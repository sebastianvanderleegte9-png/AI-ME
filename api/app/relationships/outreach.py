"""Outreach (Component 9, v2): 5 relationships a month with influencers and peers the ICP
already listens to. Warm, not cold: the sequence starts with public engagement and only
then a direct message, and every step is a Job in the founder's approval feed.

Sequence (outreach-v1), relative to day 0:
  d0   reply     public reply to their most engaged post (attention-map style)
  d3   reply     second public reply on a newer post
  d7   outreach  DM: specific, one ask, no pitch (LinkedIn or X DM via the Social interface later; drafted now)
  d14  outreach  follow-up only if no reply: one line, add something new
A reply from them moves the relationship to 'replied' and cancels remaining steps."""
from datetime import datetime, timedelta, timezone
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm, get_social
from ..models import Account, Company, Founder, Job, Relationship, VoiceProfile
from ..voice.check import check

SEQUENCE = [
    {"day": 0, "kind": "reply", "goal": "add a specific experience to their post"},
    {"day": 3, "kind": "reply", "goal": "disagree with a reason or ask a sharp question on a newer post"},
    {"day": 7, "kind": "outreach", "goal": "one direct message: reference both replies, one concrete ask (a conversation, a quote, a co-built thing), no pitch"},
    {"day": 14, "kind": "outreach", "goal": "follow-up only if silent: one line, one new thing (a number, a page, a result)"},
]
PER_MONTH = 5

DM_SYS = """You write a short direct message AS the founder, in their voice (rules and past posts below), to a
person their customers listen to. You have the person's headline and two posts of theirs the founder has already
replied to publicly. Rules: reference something specific they said; make ONE concrete ask; never pitch the
product; under 500 characters; no flattery openers. If the goal is a follow-up, one line only."""


def _fake_dm(account: Account, goal: str) -> str:
    if "follow-up" in goal:
        return "one more thing since I wrote: we published the rollout numbers. happy to share the raw data if useful."
    return (f"replied on your post about {((account.headline or 'this').split(' ')[:4] and ' '.join((account.headline or 'this').split(' ')[:4]))} — "
            f"we're seeing the same thing with brokerages. would you look at our rollout data and tell me where it's wrong? 15 minutes.")


def candidates(db: Session, company: Company, limit: int = PER_MONTH) -> list[Account]:
    busy = {r.account_id for r in db.scalars(select(Relationship).where(
        Relationship.company_id == company.id, Relationship.kind == "outreach",
        Relationship.state.not_in(["declined", "cancelled", "done"])))}
    accs = db.scalars(select(Account).where(Account.company_id == company.id, Account.cluster.in_(["influencer", "peer", "community"]),
                                            Account.icp_match_score.is_not(None)).order_by(Account.icp_match_score.desc())).all()
    return [a for a in accs if a.id not in busy][:limit]


def start(db: Session, company: Company, founder: Founder, account: Account, day0: datetime | None = None) -> Relationship:
    social, llm = get_social(), get_llm()
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder.id)).first()
    if not vp:
        raise ValueError("no voice profile")
    banned = (vp.rules or {}).get("banned_phrases", [])
    samples = [s["text"] for s in vp.samples][:20]
    d0 = (day0 or datetime.now(timezone.utc)).replace(hour=9, minute=0, second=0, microsecond=0)
    posts = social.recent_posts(channel=account.platform, handle=account.handle, limit=5)
    posts.sort(key=lambda p: -(p.get("reactions", 0) + 3 * p.get("replies", 0)))

    rel = Relationship(company_id=company.id, kind="outreach", account_id=account.id, state="active",
                       score=account.icp_match_score, reason=f"{account.cluster} the ICP follows; fit {account.icp_match_score}",
                       plan={"sequence": "outreach-v1", "cluster": account.cluster, "steps": []},
                       log=[{"at": d0.isoformat(), "event": "started", "detail": account.handle}])
    db.add(rel)
    db.flush()

    steps = []
    for i, st in enumerate(SEQUENCE):
        when = d0 + timedelta(days=st["day"])
        post = posts[min(i, len(posts) - 1)] if posts else None
        if st["kind"] == "reply" and post:
            from ..attention.targets import REPLY_SYS, _fake_reply
            system = REPLY_SYS + f"\nGoal: {st['goal']}\n\nPast posts:\n" + "\n---\n".join(samples[:6])
            txt = llm.complete(system, f"Platform: {account.platform}\nAuthor: {account.name or account.handle} ({account.headline or ''})\nPost:\n{post['text']}",
                               purpose="outreach_reply", temperature=0.6, max_tokens=300).text.strip()
            if txt.startswith("[fake:"):
                txt = _fake_reply(post["text"], account.platform)
            jin = {"reply_to_ref": post["ref"], "post_text": post["text"]}
            jtype, channel = "reply", account.platform
        else:
            system = DM_SYS + f"\nGoal: {st['goal']}\n\nVoice rules: {json.dumps({k: v for k, v in (vp.rules or {}).items() if k != 'banned_phrases'})}\n\nPast posts:\n" + "\n---\n".join(samples[:6])
            ctx = "\n".join(p["text"] for p in posts[:2])
            txt = llm.complete(system, f"Person: {account.name or account.handle} — {account.headline or ''}\nTheir posts:\n{ctx}", purpose="outreach_dm", temperature=0.6, max_tokens=300).text.strip()
            if txt.startswith("[fake:"):
                txt = _fake_dm(account, st["goal"])
            jin = {"dm_to": account.handle, "conditional": "no_reply" if st["day"] == 14 else None}
            jtype, channel = "outreach", account.platform
        res = check(txt, banned=banned, samples=samples, casing=(vp.rules or {}).get("casing"))
        job = Job(company_id=company.id, founder_id=founder.id, type=jtype, channel=channel, format=f"outreach_{st['kind']}",
                  state="pending", voice_match=res.score, scheduled_for=when,
                  input={**jin, "relationship_id": str(rel.id), "step": i, "goal": st["goal"], "account_id": str(account.id),
                         "handle": account.handle, "cluster": account.cluster},
                  output={"text": txt, "media": []})
        db.add(job)
        db.flush()
        steps.append({"step": i, "day": st["day"], "kind": st["kind"], "job_id": str(job.id), "date": when.date().isoformat()})
    rel.plan = {**rel.plan, "steps": steps}
    db.commit()
    db.refresh(rel)
    return rel


def mark_replied(db: Session, rel: Relationship, note: str = "") -> Relationship:
    """They answered. Cancel pending steps, move to 'replied'; the founder takes it from here."""
    for j in db.scalars(select(Job).where(Job.input["relationship_id"].astext == str(rel.id), Job.state == "pending")):
        j.state = "rejected"
        j.error = "cancelled: they replied"
    rel.state = "replied"
    rel.log = list(rel.log or []) + [{"at": datetime.now(timezone.utc).isoformat(), "event": "replied", "detail": note}]
    db.commit()
    db.refresh(rel)
    return rel


def stats(db: Session, company: Company) -> dict:
    rels = db.scalars(select(Relationship).where(Relationship.company_id == company.id, Relationship.kind == "outreach")).all()
    sent = sum(1 for r in rels if r.state in ("active", "replied", "done"))
    replied = sum(1 for r in rels if r.state in ("replied", "done"))
    return {"started": sent, "replied": replied, "reply_rate": round(replied / sent, 3) if sent else None, "gate": 0.25}
