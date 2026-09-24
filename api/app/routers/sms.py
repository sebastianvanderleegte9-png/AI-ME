"""Component 13: the SMS surface. Provider webhook (public, signature-checked), founder phone
linking, and admin sends for testing."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..interfaces import get_messaging
from ..models import Founder, Job, Relationship, SmsMessage, SmsState, Tool
from ..settings import settings
from ..sms import engine

router = APIRouter(tags=["sms"])
auth = [Depends(require_api_key)]


class PhoneIn(BaseModel):
    phone: str   # E.164, e.g. +13055551234


@router.post("/founders/{founder_id}/phone", dependencies=auth)
def link_phone(founder_id: uuid.UUID, body: PhoneIn, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    if not f:
        raise HTTPException(404, "founder not found")
    if not body.phone.startswith("+") or not body.phone[1:].isdigit():
        raise HTTPException(422, "phone must be E.164, e.g. +13055551234")
    code = engine.start_verify(db, f, body.phone)
    return {"sent": True, "phone": body.phone, **({"code": code} if settings.app_env in ("local", "test") else {})}


@router.post("/public/sms/inbound")
async def inbound(request: Request, db: Session = Depends(get_db)):
    """Twilio posts form-encoded fields; we verify the signature, handle, and answer empty TwiML."""
    form = dict(await request.form())
    m = get_messaging()
    if not m.verify_signature(dict(request.headers), str(request.url), form):
        raise HTTPException(403, "bad signature")
    engine.handle_inbound(db, form)
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")


@router.post("/sms/simulate", dependencies=auth)
def simulate(payload: dict, db: Session = Depends(get_db)):
    """Local testing: same as the webhook without the signature. {From, Body, NumMedia?, MediaUrl0?, MediaContentType0?}"""
    return {"replies": engine.handle_inbound(db, payload)}


@router.post("/founders/{founder_id}/sms/brief", dependencies=auth)
def brief(founder_id: uuid.UUID, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    if not f or not f.phone:
        raise HTTPException(404, "founder has no phone")
    m = engine.send_brief(db, f)
    return {"sent": m.body}


@router.post("/founders/{founder_id}/sms/friday", dependencies=auth)
def friday(founder_id: uuid.UUID, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    if not f or not f.phone:
        raise HTTPException(404, "founder has no phone")
    return {"sent": engine.send_friday(db, f).body}


@router.post("/founders/{founder_id}/sms/item/{job_id}", dependencies=auth)
def item(founder_id: uuid.UUID, job_id: uuid.UUID, db: Session = Depends(get_db)):
    f, j = db.get(Founder, founder_id), db.get(Job, job_id)
    if not f or not j:
        raise HTTPException(404, "not found")
    return {"sent": engine.send_item(db, f, j).body}


@router.post("/founders/{founder_id}/sms/tools", dependencies=auth)
def tools(founder_id: uuid.UUID, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    ts = db.scalars(select(Tool).where(Tool.company_id == f.company_id, Tool.status == "proposed").order_by(Tool.created_at.desc()).limit(3)).all()
    if not ts:
        raise HTTPException(404, "no proposed tools")
    return {"sent": engine.send_tool_ideas(db, f, ts).body}


@router.post("/founders/{founder_id}/sms/joint/{rel_id}", dependencies=auth)
def joint(founder_id: uuid.UUID, rel_id: uuid.UUID, db: Session = Depends(get_db)):
    f, r = db.get(Founder, founder_id), db.get(Relationship, rel_id)
    if not f or not r:
        raise HTTPException(404, "not found")
    return {"sent": engine.send_joint(db, f, r).body}


@router.get("/founders/{founder_id}/sms/thread", dependencies=auth)
def thread(founder_id: uuid.UUID, limit: int = 50, db: Session = Depends(get_db)):
    ms = db.scalars(select(SmsMessage).where(SmsMessage.founder_id == founder_id).order_by(SmsMessage.created_at.desc()).limit(limit)).all()
    st = db.get(SmsState, founder_id)
    return {"state": {"current": st.current, "batch": st.batch, "paused": st.paused} if st else None,
            "messages": [{"at": m.created_at, "dir": m.direction, "kind": m.kind, "body": m.body} for m in reversed(ms)]}
