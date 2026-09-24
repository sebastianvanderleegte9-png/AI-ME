from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..judgment.sequencer import commit_week, override, plan_week
from ..models import Company, Plan

router = APIRouter(prefix="/companies/{company_id}/week", tags=["sequencer"], dependencies=[Depends(require_api_key)])


class OverrideIn(BaseModel):
    changes: dict = Field(min_length=1)
    reason: str = Field(min_length=3)
    by: str = "operator"


def _company(company_id, db):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c


def _out(plan: Plan):
    w = (plan.scorecard or {}).get("weekly") or {}
    return {"plan_id": str(plan.id), "week_start": str(plan.week_start), "generated_by": plan.generated_by,
            "rules_version": plan.rules_version, "focus": w.get("focus"), "settings": w.get("settings"),
            "decisions": w.get("decisions", []), "overrides": w.get("overrides", []), "targets": plan.targets}


@router.post("")
def replan(company_id: uuid.UUID, week_start: date | None = None, db: Session = Depends(get_db)):
    """Monday: re-plan from last week's outcome. Idempotent per week."""
    c = _company(company_id, db)
    from ..learning import experiment, planner
    engine = experiment.engine_for(db, c)
    if engine == "learned":
        wp, _ = planner.propose(db, c, week_start)
    else:
        wp = plan_week(db, c, week_start)
        wp.settings["planner"] = "rules"
    out = _out(commit_week(db, c, wp))
    out["engine"] = engine
    return out


@router.get("")
def current(company_id: uuid.UUID, week_start: date | None = None, db: Session = Depends(get_db)):
    q = select(Plan).where(Plan.company_id == company_id)
    if week_start:
        q = q.where(Plan.week_start == week_start)
    p = db.scalars(q.order_by(Plan.week_start.desc())).first()
    if not p or "weekly" not in (p.scorecard or {}):
        raise HTTPException(404, "no weekly plan; POST to re-plan")
    return _out(p)


@router.post("/override")
def do_override(company_id: uuid.UUID, body: OverrideIn, week_start: date | None = None, db: Session = Depends(get_db)):
    q = select(Plan).where(Plan.company_id == company_id)
    if week_start:
        q = q.where(Plan.week_start == week_start)
    p = db.scalars(q.order_by(Plan.week_start.desc())).first()
    if not p or "weekly" not in (p.scorecard or {}):
        raise HTTPException(404, "no weekly plan to override")
    return _out(override(db, p, body.changes, body.reason, body.by))
