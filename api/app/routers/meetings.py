"""Component 15: personalized email outreach over Outlook and the meeting-booking loop.
Admin/company endpoints need the API key; the booking page under /book is public, guarded
only by its own unguessable token, same pattern as the setup wizard."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..meetings import engine, pages
from ..models import Company, Founder, Job, Meeting
from ..relationships import email_outreach
from ..settings import settings

router = APIRouter(tags=["meetings"])
auth = [Depends(require_api_key)]


class ProspectsIn(BaseModel):
    founder_id: uuid.UUID
    prospects: list[dict]   # [{name, email, company?, why}]


@router.post("/companies/{company_id}/relationships/email-outreach", status_code=201, dependencies=auth)
def start_email_outreach(company_id: uuid.UUID, body: ProspectsIn, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    f = db.get(Founder, body.founder_id)
    if not c or not f or f.company_id != c.id:
        raise HTTPException(404, "company or founder not found")
    try:
        jobs = email_outreach.propose(db, c, f, body.prospects)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return [{"job_id": str(j.id), "prospect_email": j.input.get("prospect_email"), "state": j.state, "voice_match": j.voice_match} for j in jobs]


@router.post("/jobs/{job_id}/interested", dependencies=auth)
def mark_interested(job_id: uuid.UUID, note: str = "", db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.type != "outreach" or j.channel != "email" or j.state != "executed":
        raise HTTPException(404, "no sent outreach email with that id")
    m = email_outreach.mark_interested(db, j, note)
    return _meeting_out(m)


def _meeting_out(m: Meeting) -> dict:
    return {"id": str(m.id), "state": m.state, "subject": m.subject, "prospect_email": m.prospect_email,
            "prospect_name": m.prospect_name, "proposed_slots": m.proposed_slots, "chosen_slot": m.chosen_slot,
            "confirmed_start": m.confirmed_start.isoformat() if m.confirmed_start else None,
            "calendar_event_ref": m.calendar_event_ref, "booking_token": m.booking_token,
            "booking_url": f"{settings.public_base_url}/book/{m.booking_token}"}


@router.get("/meetings/{meeting_id}", dependencies=auth)
def get_meeting(meeting_id: uuid.UUID, db: Session = Depends(get_db)):
    m = db.get(Meeting, meeting_id)
    if not m:
        raise HTTPException(404, "meeting not found")
    return _meeting_out(m)


@router.get("/companies/{company_id}/meetings", dependencies=auth)
def list_meetings(company_id: uuid.UUID, db: Session = Depends(get_db)):
    from sqlalchemy import select
    rows = db.scalars(select(Meeting).where(Meeting.company_id == company_id).order_by(Meeting.created_at.desc())).all()
    return [_meeting_out(m) for m in rows]


# ---------- public booking page ----------
@router.get("/book/{token}", response_class=HTMLResponse)
def book_show(token: str, db: Session = Depends(get_db)):
    m = engine.by_token(db, token)
    if not m:
        raise HTTPException(404)
    f = db.get(Founder, m.founder_id)
    if m.state != "sent":
        return pages.gone()
    return pages.pick(m, f.name, f.timezone)


@router.post("/book/{token}/{slot}", response_class=HTMLResponse)
def book_pick(token: str, slot: int, db: Session = Depends(get_db)):
    m = engine.by_token(db, token)
    if not m:
        raise HTTPException(404)
    f = db.get(Founder, m.founder_id)
    try:
        m = engine.choose_slot(db, m, slot)
    except ValueError:
        return pages.gone()
    return pages.picked(m, f.name)
