import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Company, Job, Metric, Plan
from ..site.engine import audit, rewrite, variant_html

router = APIRouter(tags=["site"])
auth = [Depends(require_api_key)]


class AuditIn(BaseModel):
    url: str | None = None
    html: str | None = None                 # paste when the site blocks bots
    walkthrough: dict | None = None         # {signup_steps, signup_fields, requires_card, requires_call, first_screen_after_signup, activation_email_subject, mobile_ok}


class ActivationIn(BaseModel):
    signup_id: str
    activated: bool = True


def _company(cid, db):
    c = db.get(Company, cid)
    if not c:
        raise HTTPException(404, "company not found")
    return c


def _latest_audit(company_id, db) -> dict:
    p = db.scalars(select(Plan).where(Plan.company_id == company_id).order_by(Plan.week_start.desc())).first()
    a = (p.scorecard or {}).get("site_audit") if p else None
    if not a:
        raise HTTPException(404, "no audit yet; POST /site/audit")
    return a


@router.post("/companies/{company_id}/site/audit", dependencies=auth)
def do_audit(company_id: uuid.UUID, body: AuditIn, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    if not (body.url or body.html or c.domain):
        raise HTTPException(422, "need url, html or a company domain")
    rep = audit(db, c, body.url, body.html, body.walkthrough)
    db.info["last_audit"] = rep
    return rep


@router.post("/companies/{company_id}/site/rewrite", dependencies=auth)
def do_rewrite(company_id: uuid.UUID, body: AuditIn, db: Session = Depends(get_db)):
    """Audit (or re-audit) and generate site_change jobs for the failed copy checks."""
    c = _company(company_id, db)
    rep = audit(db, c, body.url, body.html, body.walkthrough)
    return {"audit": {"overall": rep["overall"], "categories": rep["categories"]}, **rewrite(db, c, rep)}


@router.get("/companies/{company_id}/site/changes", dependencies=auth)
def changes(company_id: uuid.UUID, state: str | None = None, db: Session = Depends(get_db)):
    q = select(Job).where(Job.company_id == company_id, Job.type == "site_change")
    if state:
        q = q.where(Job.state == state)
    return [{"id": str(j.id), "element": j.format, "state": j.state, "current": j.input.get("current"),
             "proposal": j.output.get("text"), "why": j.input.get("why"), "checks": j.input.get("check_ids")}
            for j in db.scalars(q.order_by(Job.created_at))]


@router.get("/companies/{company_id}/site/export", dependencies=auth)
def export(company_id: uuid.UUID, db: Session = Depends(get_db)):
    """Approved changes as a copy-paste block for any CMS."""
    jobs = db.scalars(select(Job).where(Job.company_id == company_id, Job.type == "site_change",
                                        Job.state.in_(["approved", "edited", "executed"]))).all()
    return {j.format: j.output.get("text") for j in jobs}


@router.get("/v/{company_id}/landing")
def variant(company_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Hosted variant assembled from approved changes. Point a redirect or an A/B split here."""
    c = _company(company_id, db)
    p = db.scalars(select(Plan).where(Plan.company_id == c.id).order_by(Plan.week_start.desc())).first()
    rep = ((p.scorecard or {}).get("site_audit") if p else None) or {"snapshot": {}, "url": c.domain}
    approved = db.scalars(select(Job).where(Job.company_id == c.id, Job.type == "site_change",
                                            Job.state.in_(["approved", "edited", "executed"]))).all()
    widget = f"{str(request.base_url).rstrip('/')}/public/{c.id}/signup-widget.js"
    return Response(variant_html(c, approved, rep, widget), media_type="text/html")


# ---- activation: the before/after number ----
@router.post("/public/{company_id}/activation", status_code=201)
def activation(company_id: uuid.UUID, body: ActivationIn, db: Session = Depends(get_db)):
    """The founder's app posts this when a signup reaches first value (one line of code)."""
    from datetime import date
    if not db.get(Company, company_id):
        raise HTTPException(404, "unknown company")
    m = db.scalars(select(Metric).where(Metric.company_id == company_id, Metric.date == date.today(),
                                        Metric.name == "activations", Metric.source == "activation_hook")).first()
    if m:
        m.value = float(m.value) + 1
    else:
        db.add(Metric(company_id=company_id, date=date.today(), name="activations", value=1, source="activation_hook"))
    db.commit()
    return {"ok": True}


@router.get("/companies/{company_id}/site/activation", dependencies=auth)
def activation_rate(company_id: uuid.UUID, days: int = 28, db: Session = Depends(get_db)):
    from datetime import date, timedelta
    since = date.today() - timedelta(days=days)
    def s(name):
        return float(db.scalar(select(func.coalesce(func.sum(Metric.value), 0)).where(
            Metric.company_id == company_id, Metric.name == name, Metric.date >= since)) or 0)
    signups, acts = s("signups"), s("activations")
    return {"days": days, "signups": signups, "activations": acts, "activation_rate": round(acts / signups, 3) if signups else None}
