from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Company
from ..schemas import CompanyIn, CompanyOut

router = APIRouter(prefix="/companies", tags=["companies"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    c = Company(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    from ..learning.experiment import assign
    assign(db, c)
    return c


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(Company).order_by(Company.created_at.desc())).all()


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: UUID, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c
