from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Metric
from ..schemas import MetricOut

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[MetricOut])
def list_metrics(company_id: UUID, since: date | None = None, name: str | None = None,
                 db: Session = Depends(get_db)):
    q = select(Metric).where(Metric.company_id == company_id)
    if since:
        q = q.where(Metric.date >= since)
    if name:
        q = q.where(Metric.name == name)
    return db.scalars(q.order_by(Metric.date)).all()
