from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..judgment.render import html_to_pdf, scorecard_html
from ..judgment.scorecard import build_scorecard
from ..models import Company, Plan

router = APIRouter(prefix="/companies/{company_id}/scorecard", tags=["scorecard"],
                   dependencies=[Depends(require_api_key)])


def _company(company_id: uuid.UUID, db: Session) -> Company:
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c


def _latest_plan(company_id: uuid.UUID, db: Session) -> Plan:
    p = db.scalars(select(Plan).where(Plan.company_id == company_id).order_by(Plan.week_start.desc())).first()
    if not p:
        raise HTTPException(404, "no scorecard yet; POST to generate")
    return p


@router.post("")
def generate(company_id: uuid.UUID, week_start: date | None = None, db: Session = Depends(get_db)):
    plan = build_scorecard(db, _company(company_id, db), week_start)
    return {"plan_id": str(plan.id), "week_start": plan.week_start, "rules_version": plan.rules_version,
            "overall": plan.scorecard.get("_overall"), "scorecard": plan.scorecard,
            "sequence": plan.sequence, "targets": plan.targets}


@router.get("")
def latest(company_id: uuid.UUID, db: Session = Depends(get_db)):
    p = _latest_plan(company_id, db)
    return {"plan_id": str(p.id), "week_start": p.week_start, "rules_version": p.rules_version,
            "scorecard": p.scorecard, "sequence": p.sequence, "targets": p.targets}


@router.get(".html")
def as_html(company_id: uuid.UUID, db: Session = Depends(get_db)):
    return Response(scorecard_html(_company(company_id, db), _latest_plan(company_id, db)), media_type="text/html")


@router.get(".pdf")
def as_pdf(company_id: uuid.UUID, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    pdf = html_to_pdf(scorecard_html(c, _latest_plan(company_id, db)))
    fname = f"diagnostic-{c.name.lower().replace(' ', '-')}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
