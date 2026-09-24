"""Launch kit: create a launch -> expand its playbook into dated Jobs -> content tasks are
drafted by the voice engine from the brief (so they land in the feed like any post) ->
launch day is a checklist -> close writes results from the metrics tables.

The sequencer (R8) proposes a launch when launches are in phase; a founder can also
create one directly. Proposal = type + a date on a Tuesday/Wednesday at least 6 weeks
out for Product Hunt, 2 weeks for a feature drop."""
from datetime import date, datetime, time, timedelta, timezone
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Founder, Job, Launch, Metric, SignupSource, VoiceProfile
from ..voice.check import check
from ..voice.engine import draft_one
from ..voice.formats import FORMATS
from .playbooks import PLAYBOOKS

LEAD_DAYS = {"product_hunt": 42, "feature_drop": 14, "joint": 28, "customer_story": 14}


def propose_date(kind: str, today: date | None = None) -> date:
    d = (today or date.today()) + timedelta(days=LEAD_DAYS.get(kind, 14))
    while d.weekday() not in (1, 2):   # Tue/Wed
        d += timedelta(days=1)
    return d


def create_launch(db: Session, company: Company, founder: Founder | None, kind: str, name: str,
                  launch_date: date | None, brief: dict) -> Launch:
    if kind not in PLAYBOOKS:
        raise ValueError(f"unknown launch type {kind}")
    pb_id, _ = PLAYBOOKS[kind]
    ld = launch_date or propose_date(kind)
    if ld < date.today() + timedelta(days=3):
        raise ValueError("launch date must be at least 3 days out")
    L = Launch(company_id=company.id, founder_id=founder.id if founder else None, type=kind, name=name,
               launch_date=ld, playbook=pb_id, brief=brief, status="planned")
    db.add(L)
    db.commit()
    db.refresh(L)
    return L


def _brief_claim(L: Launch, task: dict) -> dict:
    b = L.brief or {}
    text = {"contrarian_take": b.get("why_now") or b.get("hook"), "build_log": b.get("what"),
            "customer_story": (b.get("proof") or [None])[0] if isinstance(b.get("proof"), list) else b.get("proof"),
            "number_with_lesson": (b.get("proof") or [None])[0] if isinstance(b.get("proof"), list) else b.get("proof"),
            "prediction": b.get("why_now"), "list": b.get("what"), "framework": b.get("what"),
            "question": b.get("hook"), "mistake": b.get("what")}.get(task.get("format"), b.get("hook"))
    return {"id": f"launch-{L.id}-{task['day']}", "type": "story", "text": text or f"{L.name}: {task['detail']}",
            "evidence": json.dumps(b), "customer": b.get("customer"), "number": b.get("number")}


def expand(db: Session, L: Launch) -> dict:
    """Turn the playbook into Jobs. Idempotent: skips tasks already created for this launch."""
    _, tasks = PLAYBOOKS[L.type]
    founder = db.get(Founder, L.founder_id) if L.founder_id else None
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == L.founder_id)).first() if founder else None
    existing = {(j.input or {}).get("launch_task_key") for j in db.scalars(select(Job).where(
        Job.company_id == L.company_id, Job.input["launch_id"].astext == str(L.id)))}
    created, skipped = [], []
    for t in tasks:
        key = f"{t['day']}:{t['title']}"
        if key in existing:
            skipped.append(key)
            continue
        when = datetime.combine(L.launch_date + timedelta(days=t["day"]), time(9, 0), tzinfo=timezone.utc)
        if when < datetime.now(timezone.utc) - timedelta(days=1):
            skipped.append(key)          # too late for this task; the calendar starts from today
            continue
        base_input = {"launch_id": str(L.id), "launch_task_key": key, "day": t["day"], "kind": t["kind"],
                      "title": t["title"], "detail": t["detail"]}
        if t["kind"] == "post" and founder and vp:
            claim = _brief_claim(L, t)
            text, meta = draft_one(claim, t["format"], t["channel"], vp, founder.name)
            res = check(text, banned=(vp.rules or {}).get("banned_phrases", []),
                        samples=[s["text"] for s in vp.samples][:20], casing=(vp.rules or {}).get("casing"))
            job = Job(company_id=L.company_id, founder_id=founder.id, type="post", channel=t["channel"], format=t["format"],
                      state="pending", voice_match=res.score, scheduled_for=when + timedelta(hours=3 if t["channel"] == "x" else 0),
                      input={**base_input, "claim": claim, "shape": FORMATS[t["format"]]["shape"], "length": meta},
                      output={"text": text, "media": []})
        else:
            job = Job(company_id=L.company_id, founder_id=founder.id if founder else None, type="launch_task",
                      channel="internal", format=t["kind"], state="pending", scheduled_for=when,
                      input=base_input, output={"text": f"{t['title']} — {t['detail']}"})
        db.add(job)
        created.append(job)
    if L.status == "planned":
        L.status = "active"
    db.commit()
    return {"launch_id": str(L.id), "created": len(created), "skipped": len(skipped),
            "posts": sum(1 for j in created if j.type == "post"), "tasks": sum(1 for j in created if j.type == "launch_task")}


def calendar(db: Session, L: Launch) -> list[dict]:
    jobs = db.scalars(select(Job).where(Job.company_id == L.company_id, Job.input["launch_id"].astext == str(L.id))
                      .order_by(Job.scheduled_for)).all()
    return [{"id": str(j.id), "day": (j.input or {}).get("day"), "date": j.scheduled_for.date().isoformat() if j.scheduled_for else None,
             "kind": (j.input or {}).get("kind"), "title": (j.input or {}).get("title"), "type": j.type,
             "channel": j.channel, "format": j.format, "state": j.state,
             "text": (j.output or {}).get("text", "")[:140]} for j in jobs]


def close(db: Session, L: Launch) -> Launch:
    """Write results from what the metrics tables already know for launch week."""
    start, end = L.launch_date - timedelta(days=1), L.launch_date + timedelta(days=6)
    def s(name):
        return float(db.scalar(select(func.coalesce(func.sum(Metric.value), 0)).where(
            Metric.company_id == L.company_id, Metric.name == name, Metric.date >= start, Metric.date <= end)) or 0)
    src = dict(db.execute(select(SignupSource.classified_channel, func.count()).where(
        SignupSource.company_id == L.company_id, SignupSource.created_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
        SignupSource.created_at <= datetime.combine(end, time.max, tzinfo=timezone.utc)).group_by(SignupSource.classified_channel)).all())
    done = db.scalar(select(func.count()).select_from(Job).where(Job.company_id == L.company_id,
                     Job.input["launch_id"].astext == str(L.id), Job.state == "executed")) or 0
    total = db.scalar(select(func.count()).select_from(Job).where(Job.company_id == L.company_id,
                      Job.input["launch_id"].astext == str(L.id))) or 0
    L.results = {"signups": s("signups"), "impressions_icp": round(s("impressions_icp")), "impressions": round(s("impressions")),
                 "signup_sources": {k or "unknown": v for k, v in src.items()}, "tasks_done": done, "tasks_total": total,
                 "target_signups": (L.brief or {}).get("target_signups"), "closed_at": datetime.now(timezone.utc).isoformat()}
    L.status = "closed"
    db.commit()
    db.refresh(L)
    return L
