"""Voice engine (Component 3).

  weekly interview transcript
    -> extract 15-25 claims (opinion / story / number / ...)      (LLM)
    -> pick a format per claim                                     (rules)
    -> draft per platform in the founder's voice                   (LLM, voice profile as system context)
    -> voice-match check; fail -> regenerate up to 2x, else drop   (check.py)
    -> Job(state=pending) with a scheduled slot                    (approval feed)

Nothing here publishes. Publishing happens in workers.tasks.execute_job only after
the founder's tap."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import random
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import Company, Founder, Job, VoiceProfile
from .check import check
from .formats import FORMATS, formats_for

EXTRACT_SYS = """You extract raw material from a founder interview transcript for later posts.
Return JSON: {"claims": [ {id, type, text, evidence, customer?, number?} ]}
type is one of: opinion, story, customer, product, observation, number, process, quote.
text is the claim in the founder's own words where possible (quote them). evidence is the line(s)
from the transcript it comes from. Extract 15-25 claims. Skip pleasantries and anything generic.
Prefer specific numbers, named customers, concrete mistakes, and strong opinions."""

DRAFT_SYS = """You write social posts AS the founder, in their voice. You are given:
- the founder's voice rules and real past posts (match sentence length, casing, punctuation, vocabulary, stance)
- one claim from their interview, with evidence
- a format shape and a length range
Rules: never invent facts, numbers or customers; only use what is in the claim and evidence.
No hashtags unless the founder uses them. No emoji unless the founder uses them. No generic closers.
Do not use any banned phrase. Write the post only, no title, no preamble."""


@dataclass
class DraftPlan:
    company_id: uuid.UUID
    founder_id: uuid.UUID
    transcript: str
    platforms: list[str]            # ["linkedin", "x"]
    posts_per_platform: int = 5
    week_start: datetime | None = None
    plan_id: uuid.UUID | None = None
    format_weights: dict | None = None


def extract_claims(transcript: str) -> list[dict]:
    import re
    llm = get_llm()
    out = llm.complete(EXTRACT_SYS, transcript[:60000], purpose="voice_extract", json_mode=True, max_tokens=3000).text
    try:
        claims = json.loads(out).get("claims", [])
    except json.JSONDecodeError:
        claims = []
    if not claims:  # fake LLM or parse failure: fall back to sentence-level claims so the pipeline runs
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript.replace("\n", " ")) if len(s.strip()) > 25][:20]
        import re
        claims = []
        for i, s in enumerate(sents):
            m = re.search(r"\b\d[\d,]*(?:\.\d+)?\s*(?:percent|%|agents|hours|minutes|weeks|days|x)?", s)
            claims.append({"id": f"c{i}", "type": _guess_type(s), "text": s, "evidence": s,
                           **({"number": m.group(0).strip()} if m else {})})
    for i, c in enumerate(claims):
        c.setdefault("id", f"c{i}")
        c.setdefault("type", "observation")
    return claims


def _guess_type(s: str) -> str:
    low = s.lower()
    if any(ch.isdigit() for ch in s):
        return "number"
    if any(w in low for w in ("customer", "client", "they told", "they said")):
        return "customer"
    if any(w in low for w in ("we shipped", "we built", "we changed", "launched")):
        return "product"
    if any(w in low for w in ("i think", "i believe", "wrong", "should", "never", "always")):
        return "opinion"
    if any(w in low for w in ("step", "first", "then", "process", "how we")):
        return "process"
    return "story"


def pick_formats(claims: list[dict], allowed: list[str] | None, n: int, rng: random.Random,
                 weights: dict[str, float] | None = None) -> list[tuple[dict, str]]:
    """Spread claims across formats; avoid using the same format twice in a batch when possible.
    `weights` (from the sequencer) let a format be picked more often: a weight of 2 counts as
    half a use, so it wins ties and repeats before others do."""
    weights = weights or {}
    used: dict[str, int] = {}
    picks: list[tuple[dict, str]] = []
    pool = claims[:]
    rng.shuffle(pool)
    if weights:
        # claims that can take a heavily weighted format go first, so the weight changes
        # what gets written, not just how it's shaped
        def _best_w(c):
            t = {c["type"]} | ({"number"} if c.get("number") else set()) | ({"customer"} if c.get("customer") else set())
            return max((weights.get(f, 1.0) for f in formats_for(t, allowed)), default=1.0)
        pool.sort(key=_best_w, reverse=True)
    for c in pool:
        types = {c["type"]}
        if c.get("number"):
            types.add("number")
        if c.get("customer"):
            types.add("customer")
        opts = formats_for(types, allowed)
        if not opts:
            fallback = ["list", "contrarian_take", "number_with_lesson", "question"]
            opts = [f for f in fallback if not allowed or f in allowed] or (allowed[:1] if allowed else ["list"])
        opts.sort(key=lambda f: used.get(f, 0) / max(weights.get(f, 1.0), 0.1))
        f = opts[0]
        used[f] = used.get(f, 0) + 1
        picks.append((c, f))
        if len(picks) >= n:
            break
    return picks


def draft_one(claim: dict, fmt: str, platform: str, vp: VoiceProfile, founder_name: str) -> tuple[str, dict]:
    llm = get_llm()
    lo, hi = FORMATS[fmt][f"{platform}_len"]
    samples = [s["text"] for s in vp.samples if s.get("platform") in (platform, None)][:8]
    rules = vp.rules or {}
    system = DRAFT_SYS + f"\n\nFounder: {founder_name}\nVoice rules: {json.dumps({k: v for k, v in rules.items() if k != 'banned_phrases'})}" \
             f"\nBanned phrases: {', '.join(rules.get('banned_phrases', [])[:40])}\n\nPast posts:\n" + "\n---\n".join(samples)
    user = f"Platform: {platform}. Format: {fmt}. Shape: {FORMATS[fmt]['shape']}. Length: {lo}-{hi} characters.\n\n" \
           f"Claim: {claim['text']}\nEvidence: {claim.get('evidence', '')}\n" + \
           (f"Customer: {claim['customer']}\n" if claim.get("customer") else "") + \
           (f"Number: {claim['number']}\n" if claim.get("number") else "")
    text = llm.complete(system, user, purpose="voice_draft", temperature=0.7, max_tokens=700).text.strip()
    if text.startswith("[fake:"):
        # fake LLM: produce a plausibly shaped draft from the claim so the feed and checks are exercised
        text = _fake_draft(claim, fmt, platform, hi)
    return text, {"lo": lo, "hi": hi}


def _fake_draft(claim: dict, fmt: str, platform: str, hi: int) -> str:
    body = claim["text"].rstrip(".")
    shapes = {
        "contrarian_take": f"most people think the opposite.\n\n{body}.\n\nwe learned that the hard way.",
        "number_with_lesson": f"{claim.get('number') or 'one number'}.\n\n{body}.\n\nthat's the whole lesson.",
        "question": f"{body}?\n\nwe think yes. what has your experience been.",
        "list": f"three things we learned\n\n1. {body}\n2. it took longer than we planned\n3. we would do it again",
    }
    t = shapes.get(fmt, f"{body}.\n\nhere is what we did about it.")
    return t[:hi]


def run_voice_engine(db: Session, plan: DraftPlan) -> dict:
    company = db.get(Company, plan.company_id)
    founder = db.get(Founder, plan.founder_id)
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == plan.founder_id)).first()
    if not (company and founder and vp):
        raise ValueError("company, founder and voice profile must exist (run intake)")

    rng = random.Random(str(plan.founder_id) + (plan.week_start or datetime.now(timezone.utc)).isoformat()[:10])
    claims = extract_claims(plan.transcript)
    banned = (vp.rules or {}).get("banned_phrases", [])
    samples = [s["text"] for s in vp.samples][:20]
    allowed = (vp.rules or {}).get("formats_allowed") or None

    created, dropped, checks = [], [], []
    start = (plan.week_start or datetime.now(timezone.utc)).replace(hour=9, minute=0, second=0, microsecond=0)
    for platform in plan.platforms:
        picks = pick_formats(claims, allowed, plan.posts_per_platform, rng, plan.format_weights)
        slot = 0
        for claim, fmt in picks:
            text, meta = None, {}
            result = None
            for attempt in range(3):
                text, meta = draft_one(claim, fmt, platform, vp, founder.name)
                result = check(text, banned=banned, samples=samples, casing=(vp.rules or {}).get("casing"))
                checks.append({"format": fmt, "platform": platform, "attempt": attempt, **result.__dict__})
                if result.passed:
                    break
            if not result or not result.passed:
                dropped.append({"claim": claim["id"], "format": fmt, "platform": platform,
                                "reason": result.banned_hits or result.pattern_hits if result else "no result"})
                continue
            # schedule: one post per weekday morning per platform, X 3h after LinkedIn
            when = start + timedelta(days=slot % 5, hours=3 if platform == "x" else 0)
            slot += 1
            job = Job(company_id=company.id, plan_id=plan.plan_id, founder_id=founder.id, type="post",
                      channel=platform, format=fmt, state="pending", voice_match=result.score,
                      scheduled_for=when,
                      input={"claim": claim, "format": fmt, "shape": FORMATS[fmt]["shape"], "length": meta,
                             "check": {"pattern_hits": result.pattern_hits, "similarity": result.similarity}},
                      output={"text": text, "media": []})
            db.add(job)
            created.append(job)
    db.commit()
    return {"claims": len(claims), "created": [str(j.id) for j in created], "dropped": dropped,
            "checks": len(checks), "avg_voice_match": round(sum(j.voice_match for j in created) / len(created), 3) if created else None}
