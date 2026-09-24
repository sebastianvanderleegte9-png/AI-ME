from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..metrics.pull import pull_company
from ..metrics.report import report_html, rollup, share_card_html, week_bounds, write_outcome
from ..metrics.signup import classify
from ..models import Company, Plan, SignupSource, VoiceProfile
from ..voice.visuals import render_png

router = APIRouter(tags=["report"])
auth = [Depends(require_api_key)]


def _company(company_id: uuid.UUID, db: Session) -> Company:
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c


@router.post("/companies/{company_id}/metrics/pull", dependencies=auth)
def pull(company_id: uuid.UUID, today: date | None = None, db: Session = Depends(get_db)):
    return pull_company(db, _company(company_id, db), today)


@router.get("/companies/{company_id}/report", dependencies=auth)
def report_json(company_id: uuid.UUID, week_of: date | None = None, db: Session = Depends(get_db)):
    return rollup(db, _company(company_id, db), week_of)


@router.post("/companies/{company_id}/report/close-week", dependencies=auth)
def close_week(company_id: uuid.UUID, week_of: date | None = None, db: Session = Depends(get_db)):
    """Friday: write the outcome row (plan vs actual). This is the dataset."""
    try:
        c = _company(company_id, db)
        o = write_outcome(db, c, week_of)
        from ..learning.dataset import build_week
        build_week(db, c, o.week_start)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"outcome_id": str(o.id), "week_start": str(o.week_start), "targets": o.targets, "actuals": o.actuals,
            "delta": o.delta, "approval_rate": o.approval_rate, "edit_rate": o.edit_rate}


@router.get("/companies/{company_id}/report.html", dependencies=auth)
def report_page(company_id: uuid.UUID, week_of: date | None = None, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    start, _ = week_bounds(week_of)
    plan = db.scalars(select(Plan).where(Plan.company_id == c.id, Plan.week_start <= start).order_by(Plan.week_start.desc())).first()
    return Response(report_html(c, rollup(db, c, week_of), plan), media_type="text/html")


@router.get("/companies/{company_id}/report/card.png", dependencies=auth)
def share_card(company_id: uuid.UUID, week_of: date | None = None, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.company_id == c.id)).first()
    brand = (vp.rules or {}).get("visual") if vp else None
    html = share_card_html(c, rollup(db, c, week_of), brand)
    return Response(render_png(html, size=(1200, 630)), media_type="image/png")


# ---------- signup source: public receiver + embeddable widget (no API key; keyed by company id) ----------
class SignupIn(BaseModel):
    answer: str
    signup_id: str | None = None


@router.post("/public/{company_id}/signup-source", status_code=201)
def receive_signup(company_id: uuid.UUID, body: SignupIn, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, "unknown company")
    label, by = classify(body.answer)
    row = SignupSource(company_id=company_id, signup_id=body.signup_id, answer_text=body.answer[:500],
                       classified_channel=label, classified_by=by)
    db.add(row)
    db.commit()
    return {"channel": label, "classified_by": by}


@router.get("/public/{company_id}/signup-widget.js")
def widget(company_id: uuid.UUID, request: Request):
    """One <script> tag on the founder's signup page. Adds the question under any form
    with data-me-signup, posts the answer on submit. No cookies, no tracking."""
    base = str(request.base_url).rstrip("/")
    js = f"""(function(){{
  var forms=document.querySelectorAll('form[data-me-signup]');
  forms.forEach(function(f){{
    var w=document.createElement('label');w.style.display='block';w.style.margin='8px 0';
    w.innerHTML='How did you hear about us? <input name="me_source" style="display:block;width:100%;margin-top:4px" maxlength="200">';
    f.appendChild(w);
    f.addEventListener('submit',function(){{
      var v=f.querySelector('[name=me_source]').value; if(!v) return;
      var id=(f.querySelector('[name=email]')||{{}}).value||null;
      navigator.sendBeacon('{base}/public/{company_id}/signup-source',
        new Blob([JSON.stringify({{answer:v,signup_id:id}})],{{type:'application/json'}}));
    }});
  }});
}})();"""
    return Response(js, media_type="application/javascript")
