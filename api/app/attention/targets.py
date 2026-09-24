"""Daily targets: 10 live threads the ICP is reading, each with a reply drafted in the
founder's voice, delivered as Jobs(type=reply) in the same approval feed as posts.

Selection = top accounts by ICP fit, weighted toward buyers and influencers, skipping
anyone replied to in the last 7 days, then their most recent post with engagement.
A reply that adds nothing (no claim, no number, no question) is not drafted."""
from datetime import datetime, timedelta, timezone
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm, get_social
from ..models import Account, Company, Founder, Job, VoiceProfile
from ..voice.check import check

CLUSTER_WEIGHT = {"buyer": 1.0, "influencer": 0.9, "community": 0.7, "peer": 0.5}
COOLDOWN_DAYS = 7

REPLY_SYS = """You reply to a post AS the founder, in their voice (rules and past posts below).
A reply is worth posting only if it adds one of: a specific experience, a number, a disagreement
with a reason, or a sharp question. If it would just agree or compliment, output exactly: SKIP.
Max 280 characters on X, 500 on LinkedIn. No hashtags, no emoji unless the founder uses them.
Never mention the founder's product by name unless the post is about that problem."""


def _fake_reply(post_text: str, platform: str) -> str:
    topic = post_text.split(" — ")[0]
    return (f"we hit this with {topic.lower()} last quarter. the fix was smaller than we expected: "
            f"ship to the ten loudest users first, then widen.")[: (280 if platform == "x" else 500)]


def pick_accounts(db: Session, company_id: uuid.UUID, platform: str, n: int) -> list[Account]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)).isoformat()
    accs = db.scalars(select(Account).where(Account.company_id == company_id, Account.platform == platform,
                                            Account.icp_match_score.is_not(None))).all()
    def key(a: Account):
        last = (a.interaction or {}).get("last_replied_at")
        cooled = 0 if (last and last > cutoff) else 1
        return (cooled, (a.icp_match_score or 0) * CLUSTER_WEIGHT.get(a.cluster or "peer", 0.5))
    accs.sort(key=key, reverse=True)
    return [a for a in accs if not ((a.interaction or {}).get("last_replied_at", "") > cutoff)][:n]


def build_daily_targets(db: Session, founder: Founder, platforms: list[str] = ("linkedin", "x"),
                        per_platform: int = 5, day: datetime | None = None) -> dict:
    social, llm = get_social(), get_llm()
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder.id)).first()
    if not vp:
        raise ValueError("no voice profile; run intake")
    banned = (vp.rules or {}).get("banned_phrases", [])
    samples = [s["text"] for s in vp.samples][:20]
    when = (day or datetime.now(timezone.utc)).replace(hour=8, minute=30, second=0, microsecond=0)

    created, skipped = [], []
    for platform in platforms:
        for acc in pick_accounts(db, founder.company_id, platform, per_platform * 2):
            if sum(1 for j in created if j.channel == platform) >= per_platform:
                break
            posts = [p for p in social.recent_posts(channel=platform, handle=acc.handle, limit=5)
                     if (p.get("replies", 0) + p.get("reactions", 0)) > 0]
            if not posts:
                skipped.append({"handle": acc.handle, "reason": "no engaged posts"})
                continue
            post = max(posts, key=lambda p: p.get("reactions", 0) + 3 * p.get("replies", 0))
            system = REPLY_SYS + f"\n\nVoice rules: {json.dumps({k: v for k, v in (vp.rules or {}).items() if k != 'banned_phrases'})}" \
                     f"\nBanned: {', '.join(banned[:40])}\n\nPast posts:\n" + "\n---\n".join(samples[:6])
            user = f"Platform: {platform}\nAuthor: {acc.name or acc.handle} ({acc.headline or ''})\nPost:\n{post['text']}"
            reply = llm.complete(system, user, purpose="reply_draft", temperature=0.6, max_tokens=300).text.strip()
            if reply.startswith("[fake:"):
                reply = _fake_reply(post["text"], platform)
            if reply.upper().startswith("SKIP"):
                skipped.append({"handle": acc.handle, "reason": "nothing to add"})
                continue
            res = check(reply, banned=banned, samples=samples, casing=(vp.rules or {}).get("casing"))
            if not res.passed:
                skipped.append({"handle": acc.handle, "reason": res.banned_hits or res.pattern_hits})
                continue
            job = Job(company_id=founder.company_id, founder_id=founder.id, type="reply", channel=platform,
                      format="reply", state="pending", voice_match=res.score, scheduled_for=when,
                      input={"reply_to_ref": post["ref"], "account_id": str(acc.id), "handle": acc.handle,
                             "cluster": acc.cluster, "icp_match": acc.icp_match_score,
                             "post_text": post["text"], "post_engagement": {"replies": post.get("replies"), "reactions": post.get("reactions")}},
                      output={"text": reply, "media": []})
            db.add(job)
            created.append(job)
    db.commit()
    return {"created": [str(j.id) for j in created], "skipped": skipped,
            "by_platform": {p: sum(1 for j in created if j.channel == p) for p in platforms}}


def record_reply_executed(db: Session, job: Job) -> None:
    """Called by the worker after a reply publishes: stamps the account so it cools down."""
    acc_id = (job.input or {}).get("account_id")
    if not acc_id:
        return
    acc = db.get(Account, uuid.UUID(acc_id))
    if acc:
        it = dict(acc.interaction or {})
        it["last_replied_at"] = datetime.now(timezone.utc).isoformat()
        it["replies"] = int(it.get("replies", 0)) + 1
        acc.interaction = it
