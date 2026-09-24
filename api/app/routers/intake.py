"""Component 1 endpoints: add founders, run intake, read and edit the ICP.
Account OAuth lands in the web app; the API stores the resulting handles/tokens."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..intake.pipeline import IntakeInput, run_intake
from ..models import ICP, Company, Founder, VoiceProfile

router = APIRouter(tags=["intake"], dependencies=[Depends(require_api_key)])


class FounderIn(BaseModel):
    name: str
    email: str | None = None
    linkedin_handle: str | None = None
    x_handle: str | None = None


class FounderOut(FounderIn):
    id: uuid.UUID
    company_id: uuid.UUID
    voice_profile_id: uuid.UUID | None


class IntakeIn(BaseModel):
    site_url: str
    docs_urls: list[str] = Field(default_factory=list)
    best_customers: list[dict] = Field(min_length=1, max_length=10)
    founder_handles: list[dict] = Field(default_factory=list)
    site_text: str | None = None


class ICPOut(BaseModel):
    id: uuid.UUID
    description: str | None
    best_customers: list
    firmographics: dict
    personas: list
    version: int


class ICPEdit(BaseModel):
    description: str | None = None
    firmographics: dict | None = None
    personas: list | None = None


@router.post("/companies/{company_id}/founders", response_model=FounderOut, status_code=201)
def add_founder(company_id: uuid.UUID, body: FounderIn, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, "company not found")
    f = Founder(company_id=company_id, **body.model_dump())
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.get("/companies/{company_id}/founders", response_model=list[FounderOut])
def list_founders(company_id: uuid.UUID, db: Session = Depends(get_db)):
    return db.scalars(select(Founder).where(Founder.company_id == company_id)).all()


@router.post("/companies/{company_id}/intake")
def intake(company_id: uuid.UUID, body: IntakeIn, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(404, "company not found")
    handles = body.founder_handles or [
        {"founder_id": str(f.id), "linkedin_handle": f.linkedin_handle, "x_handle": f.x_handle}
        for f in db.scalars(select(Founder).where(Founder.company_id == company_id))]
    try:
        return run_intake(db, IntakeInput(company_id=company_id, site_url=body.site_url,
                                          docs_urls=body.docs_urls, best_customers=body.best_customers,
                                          founder_handles=handles, site_text=body.site_text))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/companies/{company_id}/icp", response_model=ICPOut)
def get_icp(company_id: uuid.UUID, db: Session = Depends(get_db)):
    icp = db.scalars(select(ICP).where(ICP.company_id == company_id).order_by(ICP.version.desc())).first()
    if not icp:
        raise HTTPException(404, "no icp yet; run intake")
    return icp


@router.patch("/companies/{company_id}/icp", response_model=ICPOut)
def edit_icp(company_id: uuid.UUID, body: ICPEdit, db: Session = Depends(get_db)):
    """The founder edits the ICP; every edit bumps the version so the scorecard and
    attention map know which ICP they were computed against."""
    icp = db.scalars(select(ICP).where(ICP.company_id == company_id).order_by(ICP.version.desc())).first()
    if not icp:
        raise HTTPException(404, "no icp yet; run intake")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(icp, k, v)
    icp.version += 1
    db.commit()
    db.refresh(icp)
    return icp


@router.get("/founders/{founder_id}/voice")
def get_voice(founder_id: uuid.UUID, db: Session = Depends(get_db)):
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder_id)).first()
    if not vp:
        raise HTTPException(404, "no voice profile yet; run intake")
    return {"id": str(vp.id), "samples": vp.samples, "rules": vp.rules, "version": vp.version}
