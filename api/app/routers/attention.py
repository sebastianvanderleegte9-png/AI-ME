from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..attention.map import build_map
from ..attention.targets import build_daily_targets
from ..auth import require_api_key
from ..db import get_db
from ..models import Account, Company, Founder

router = APIRouter(tags=["attention"], dependencies=[Depends(require_api_key)])


class TargetsIn(BaseModel):
    platforms: list[str] = Field(default=["linkedin", "x"])
    per_platform: int = Field(default=5, ge=1, le=10)
    day: datetime | None = None


@router.post("/companies/{company_id}/attention-map")
def build(company_id: uuid.UUID, platforms: str = "linkedin,x", db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    try:
        return build_map(db, c, [p for p in platforms.split(",") if p]).__dict__
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/companies/{company_id}/attention-map")
def get_map(company_id: uuid.UUID, cluster: str | None = None, platform: str | None = None,
            limit: int = 100, db: Session = Depends(get_db)):
    q = select(Account).where(Account.company_id == company_id)
    if cluster:
        q = q.where(Account.cluster == cluster)
    if platform:
        q = q.where(Account.platform == platform)
    accs = db.scalars(q.order_by(Account.icp_match_score.desc().nulls_last()).limit(limit)).all()
    counts = dict(db.execute(select(Account.cluster, func.count()).where(Account.company_id == company_id)
                             .group_by(Account.cluster)).all())
    return {"clusters": counts, "accounts": [
        {"id": str(a.id), "platform": a.platform, "handle": a.handle, "name": a.name, "headline": a.headline,
         "org": a.org, "cluster": a.cluster, "icp_match": a.icp_match_score, "follows": a.follows_count,
         "interaction": a.interaction} for a in accs]}


@router.post("/founders/{founder_id}/targets")
def targets(founder_id: uuid.UUID, body: TargetsIn, db: Session = Depends(get_db)):
    f = db.get(Founder, founder_id)
    if not f:
        raise HTTPException(404, "founder not found")
    try:
        return build_daily_targets(db, f, body.platforms, body.per_platform, body.day)
    except ValueError as e:
        raise HTTPException(422, str(e))
