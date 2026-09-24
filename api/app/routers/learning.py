from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..learning import dataset, experiment, planner
from ..models import Company

router = APIRouter(prefix="/learning", tags=["learning"], dependencies=[Depends(require_api_key)])


class DefaultIn(BaseModel):
    engine: str   # rules | learned


@router.get("/dataset")
def dataset_size(db: Session = Depends(get_db)):
    return dataset.size(db)


@router.post("/dataset/build")
def dataset_build(week_start: date, db: Session = Depends(get_db)):
    return {"rows_built": dataset.build_all(db, week_start)}


@router.get("/experiment")
def evaluate(db: Session = Depends(get_db)):
    return {**experiment.evaluate(db), "default": "learned" if experiment.promoted(db) else "rules"}


@router.post("/experiment/assign/{company_id}")
def assign(company_id: uuid.UUID, arm: str | None = None, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    if arm and arm not in ("rules", "learned"):
        raise HTTPException(422, "arm must be rules or learned")
    return {"company_id": str(c.id), "arm": experiment.assign(db, c, arm)}


@router.post("/experiment/default")
def set_default(body: DefaultIn, db: Session = Depends(get_db)):
    """Promotion is a deliberate act: only allowed when the evaluation says learned wins (or reverting to rules)."""
    if body.engine not in ("rules", "learned"):
        raise HTTPException(422, "engine must be rules or learned")
    if body.engine == "learned" and not experiment.evaluate(db)["learned_wins"]:
        raise HTTPException(409, "learned has not won the experiment; promotion refused")
    experiment.set_default(db, body.engine)
    return {"default": body.engine}


@router.get("/companies/{company_id}/neighbours")
def neighbours(company_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return [n.__dict__ for n in planner.neighbours(db, c)]


@router.post("/companies/{company_id}/preview")
def preview(company_id: uuid.UUID, week_start: date | None = None, db: Session = Depends(get_db)):
    """What the learned planner WOULD do this week, with the neighbours it drew on. Does not commit."""
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    wp, ns = planner.propose(db, c, week_start)
    return {"settings": wp.settings, "decisions": [d.__dict__ for d in wp.decisions],
            "neighbours": [n.__dict__ for n in ns[:10]], "engine": experiment.engine_for(db, c)}
