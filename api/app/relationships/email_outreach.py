"""Personalized cold/warm email outreach over the founder's own Outlook (Component 15).
Each prospect becomes an ordinary pending Job (type=outreach, channel=email) — it goes through
the exact same approval feed as a post or a DM: it shows up in the brief, 'yes 1 3' sends it,
'no 2' drops it, free text edits it. Sending happens in execute_job, same guard rails as
everything else (approved-only, company must be active)."""
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import Company, Founder, Job, VoiceProfile
from ..voice.check import check

EMAIL_SYS = """You write a short first-touch or warm outreach email AS the founder, in their voice
(rules and past posts below), to a real prospect who looks like a good customer. Reference the
specific reason they're a fit, make one concrete, low-friction ask (a 15-minute call, a quick reply),
never a hard pitch, under 150 words, no subject line, no flattery openers."""


def _fake_email(prospect_name: str, company_name: str, why: str) -> str:
    return (f"Hi {prospect_name.split()[0] if prospect_name else 'there'} — reaching out because {why or f'{company_name} looks like a strong fit for what we do'}. "
            f"Worth a quick 15-minute call to see if it's useful? Happy to work around your schedule.")


def propose(db: Session, company: Company, founder: Founder, prospects: list[dict]) -> list[Job]:
    """prospects: [{name, email, company?, why}]. Returns one pending Job per valid prospect."""
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder.id)).first()
    if not vp:
        raise ValueError("no voice profile yet — run intake first")
    banned = (vp.rules or {}).get("banned_phrases", [])
    samples = [s["text"] for s in vp.samples][:20]
    llm = get_llm()
    jobs = []
    for p in prospects:
        email = (p.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        name, pco, why = p.get("name", "").strip(), p.get("company", "").strip(), p.get("why", "").strip()
        system = EMAIL_SYS + f"\n\nVoice rules: {json.dumps({k: v for k, v in (vp.rules or {}).items() if k != 'banned_phrases'})}\n\nPast posts:\n" + "\n---\n".join(samples[:6])
        user = f"Prospect: {name or email}{f' ({pco})' if pco else ''}\nWhy they're a fit: {why}"
        txt = llm.complete(system, user, purpose="email_outreach", temperature=0.6, max_tokens=300).text.strip()
        if txt.startswith("[fake:"):
            txt = _fake_email(name, pco or company.name, why)
        res = check(txt, banned=banned, samples=samples, casing=(vp.rules or {}).get("casing"))
        job = Job(company_id=company.id, founder_id=founder.id, type="outreach", channel="email", format="email_outreach",
                  state="pending", voice_match=res.score,
                  input={"prospect_name": name, "prospect_email": email, "prospect_company": pco, "why": why, "subject": f"Quick question, {name.split()[0] if name else pco or 'there'}"},
                  output={"text": txt, "media": []})
        db.add(job)
        jobs.append(job)
    db.commit()
    for j in jobs:
        db.refresh(j)
    return jobs


def mark_interested(db: Session, job: Job, note: str = "") -> "Meeting":  # noqa: F821
    """The prospect replied wanting to talk. Propose a meeting automatically from the same
    context that made the first email land."""
    from ..meetings.engine import propose as propose_meeting
    company = db.get(Company, job.company_id)
    founder = db.get(Founder, job.founder_id)
    i = job.input or {}
    m = propose_meeting(db, company, founder, prospect_name=i.get("prospect_name") or i.get("prospect_email"),
                        prospect_email=i.get("prospect_email"), subject=i.get("subject") or f"Chat with {company.name}",
                        context=note or i.get("why", ""), job=job)
    return m
