from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..launch.kit import calendar, close, create_launch, expand, propose_date
from ..launch.playbooks import PLAYBOOKS
from ..models import Company, Founder, Launch

router = APIRouter(tags=["launches"], dependencies=[Depends(require_api_key)])


class LaunchIn(BaseModel):
    type: str
    name: str = Field(min_length=3)
    launch_date: date | None = None
    founder_id: uuid.UUID | None = None
    brief: dict = Field(default_factory=dict)   # {what, why_now, hook, proof[], number?, customer?, target_signups}
    expand: bool = True


def _out(L: Launch):
    return {"id": str(L.id), "type": L.type, "name": L.name, "launch_date": str(L.launch_date), "playbook": L.playbook,
            "status": L.status, "brief": L.brief, "results": L.results}


@router.get("/launch-playbooks")
def playbooks():
    return {k: {"id": v[0], "tasks": len(v[1]), "first_day": min(t["day"] for t in v[1]), "proposed_date": str(propose_date(k))}
            for k, v in PLAYBOOKS.items()}


@router.post("/companies/{company_id}/launches", status_code=201)
def create(company_id: uuid.UUID, body: LaunchIn, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    f = db.get(Founder, body.founder_id) if body.founder_id else db.scalars(select(Founder).where(Founder.company_id == c.id)).first()
    try:
        L = create_launch(db, c, f, body.type, body.name, body.launch_date, body.brief)
    except ValueError as e:
        raise HTTPException(422, str(e))
    expanded = expand(db, L) if body.expand else None
    out = _out(L)
    if expanded:
        out["expanded"] = expanded
    return out


@router.get("/companies/{company_id}/launches")
def list_launches(company_id: uuid.UUID, db: Session = Depends(get_db)):
    return [_out(L) for L in db.scalars(select(Launch).where(Launch.company_id == company_id).order_by(Launch.launch_date))]


@router.get("/launches/{launch_id}")
def get_launch(launch_id: uuid.UUID, db: Session = Depends(get_db)):
    L = db.get(Launch, launch_id)
    if not L:
        raise HTTPException(404, "launch not found")
    return {**_out(L), "calendar": calendar(db, L)}


@router.post("/launches/{launch_id}/expand")
def do_expand(launch_id: uuid.UUID, db: Session = Depends(get_db)):
    L = db.get(Launch, launch_id)
    if not L:
        raise HTTPException(404, "launch not found")
    return expand(db, L)


@router.post("/launches/{launch_id}/close")
def do_close(launch_id: uuid.UUID, db: Session = Depends(get_db)):
    L = db.get(Launch, launch_id)
    if not L:
        raise HTTPException(404, "launch not found")
    return _out(close(db, L))
