"""Component 3 endpoints: submit the weekly interview, read the approval feed, get
per-founder approval/edit/rejection rates, edit voice rules, preview a visual."""
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Founder, Job, VoiceProfile
from ..voice.engine import DraftPlan, run_voice_engine
from ..voice.formats import FORMATS
from ..voice.visuals import render_png, visual_for_job

router = APIRouter(tags=["voice"], dependencies=[Depends(require_api_key)])


class InterviewIn(BaseModel):
    transcript: str = Field(min_length=200)
    platforms: list[str] = Field(default=["linkedin", "x"])
    posts_per_platform: int = Field(default=5, ge=1, le=12)
    week_start: datetime | None = None
    plan_id: uuid.UUID | None = None


class RulesIn(BaseModel):
    tone: str | None = None
    casing: str | None = None                  # "lower" | None
    banned_phrases_add: list[str] = Field(default_factory=list)
    banned_phrases_remove: list[str] = Field(default_factory=list)
    formats_allowed: list[str] | None = None
    visual: dict | None = None                  # {bg, fg, accent, font, logo_url}


@router.post("/founders/{founder_id}/interview")
def interview(founder_id: uuid.UUID, body: InterviewIn, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    if not f:
        raise HTTPException(404, "founder not found")
    bad = [p for p in body.platforms if p not in ("linkedin", "x")]
    if bad:
        raise HTTPException(422, f"unknown platforms {bad}")
    weekly = {}
    plan_id = body.plan_id
    if plan_id is None:
        from ..models import Plan
        from datetime import date, timedelta
        ws = date.today() - timedelta(days=date.today().weekday())
        p = db.scalars(select(Plan).where(Plan.company_id == f.company_id, Plan.week_start == ws)).first()
        if p:
            plan_id = p.id
            weekly = ((p.scorecard or {}).get("weekly") or {}).get("settings") or {}
    try:
        return run_voice_engine(db, DraftPlan(company_id=f.company_id, founder_id=f.id, transcript=body.transcript,
                                              platforms=body.platforms,
                                              posts_per_platform=weekly.get("posts_per_platform", body.posts_per_platform),
                                              week_start=body.week_start, plan_id=plan_id,
                                              format_weights=weekly.get("format_weights")))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/founders/{founder_id}/feed")
def feed(founder_id: uuid.UUID, state: str = "pending", db: Session = Depends(get_db)):
    """The approval feed: what the founder sees on their phone. Oldest slot first."""
    q = select(Job).where(Job.founder_id == founder_id, Job.type.in_(["post", "reply", "launch_task", "outreach"]))
    if state != "all":
        q = q.where(Job.state == state)
    jobs = db.scalars(q.order_by(Job.scheduled_for.nulls_last(), Job.created_at)).all()
    return [{"id": str(j.id), "channel": j.channel, "format": j.format, "state": j.state,
             "scheduled_for": j.scheduled_for, "voice_match": j.voice_match,
             "text": j.output.get("text"), "media": j.output.get("media", []),
             "why": {"claim": j.input.get("claim", {}).get("text"), "shape": j.input.get("shape")},
             "launch": {"id": j.input["launch_id"], "day": j.input.get("day"), "title": j.input.get("title")} if j.input.get("launch_id") else None}
            for j in jobs]


@router.get("/founders/{founder_id}/voice/stats")
def voice_stats(founder_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = db.execute(select(Job.format, Job.state, func.count()).where(
        Job.founder_id == founder_id, Job.type == "post").group_by(Job.format, Job.state)).all()
    by_fmt: dict[str, dict] = {}
    tot = {"approved": 0, "edited": 0, "rejected": 0, "pending": 0, "executed": 0, "failed": 0}
    for fmt, st, n in rows:
        by_fmt.setdefault(fmt, {k: 0 for k in tot})[st] = n
        tot[st] += n
    def rates(d):
        decided = d["approved"] + d["edited"] + d["rejected"] + d["executed"]
        ok = d["approved"] + d["edited"] + d["executed"]
        return {"decided": decided, "approval_rate": round(ok / decided, 3) if decided else None,
                "edit_rate": round(d["edited"] / ok, 3) if ok else None}
    return {"overall": {**tot, **rates(tot)}, "by_format": {f: {**d, **rates(d)} for f, d in by_fmt.items()},
            "gate": {"approval_rate_min": 0.7, "edit_rate_max": 0.2}}


@router.patch("/founders/{founder_id}/voice/rules")
def edit_rules(founder_id: uuid.UUID, body: RulesIn, db: Session = Depends(get_db)):
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder_id)).first()
    if not vp:
        raise HTTPException(404, "no voice profile; run intake")
    rules = dict(vp.rules or {})
    for k in ("tone", "casing", "formats_allowed", "visual"):
        v = getattr(body, k)
        if v is not None:
            rules[k] = v
    banned = set(rules.get("banned_phrases", []))
    banned |= set(body.banned_phrases_add)
    banned -= set(body.banned_phrases_remove)
    rules["banned_phrases"] = sorted(banned)
    vp.rules = rules
    vp.version += 1
    db.commit()
    return {"version": vp.version, "rules": vp.rules}


@router.get("/formats")
def formats():
    return {k: {"needs": v["needs"], "shape": v["shape"], "visual": v["visual"]} for k, v in FORMATS.items()}


@router.get("/jobs/{job_id}/visual.png")
def visual_png(job_id: uuid.UUID, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == j.founder_id)).first()
    brand = (vp.rules or {}).get("visual", {}) if vp else {}
    f = db.get(Founder, j.founder_id)
    html = visual_for_job(j.input, j.output, brand, j.channel, footer=f.name if f else "")
    if not html:
        raise HTTPException(404, "this post has no visual (text carries it)")
    return Response(render_png(html, j.channel), media_type="image/png")
