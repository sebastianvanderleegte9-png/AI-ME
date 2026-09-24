"""Jobs are the unit of everything the product does. This router is the approval feed's
backend: create (by the product), list (for the feed), decide (the founder's tap), and
enqueue for execution. Component 3 adds voice-match gating and scheduling; the shape
does not change."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Job
from ..queue import default_q, publish_q
from ..schemas import JobDecision, JobIn, JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])

EXECUTABLE_STATES = {"approved", "edited"}


def _diff(before: dict, after: dict) -> dict:
    return {k: {"before": before.get(k), "after": after.get(k)}
            for k in set(before) | set(after) if before.get(k) != after.get(k)}


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobIn, db: Session = Depends(get_db)):
    j = Job(**body.model_dump())
    db.add(j)
    db.commit()
    db.refresh(j)
    if j.type == "heartbeat":
        # Heartbeat needs no approval; it proves the queue end to end (Component 0 done-when).
        default_q.enqueue("workers.tasks.heartbeat", str(j.id))
    return j


@router.get("", response_model=list[JobOut])
def list_jobs(company_id: UUID, state: str | None = None, db: Session = Depends(get_db)):
    q = select(Job).where(Job.company_id == company_id)
    if state:
        q = q.where(Job.state == state)
    return db.scalars(q.order_by(Job.scheduled_for.nulls_last(), Job.created_at)).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.post("/{job_id}/decision", response_model=JobOut)
def decide(job_id: UUID, body: JobDecision, db: Session = Depends(get_db)):
    """Principle 3: the founder approves, the product ships. Every edit is a training signal."""
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    if j.state not in ("pending",):
        raise HTTPException(409, f"job is {j.state}, not pending")

    if body.decision == "reject":
        j.state = "rejected"
    elif body.edited_output is not None and body.edited_output != j.output:
        j.approval_diff = _diff(j.output, body.edited_output)
        j.output = body.edited_output
        j.state = "edited"
    else:
        j.state = "approved"

    db.commit()
    db.refresh(j)
    if j.state in EXECUTABLE_STATES and j.type in ("launch_task", "site_change"):
        # a checklist item: the tap IS the execution
        j.state, j.platform_ref, j.executed_at = "executed", f"task-{j.id.hex[:8]}", datetime.now(timezone.utc)
        db.commit()
        db.refresh(j)
        return j
    if j.state in EXECUTABLE_STATES:
        # Principle 3 + scheduling: publish at the slot, not at the tap.
        delay = (j.scheduled_for - datetime.now(timezone.utc)).total_seconds() if j.scheduled_for else 0
        if delay > 0:
            publish_q.enqueue_in(timedelta(seconds=delay), "workers.tasks.execute_job", str(j.id))
        else:
            publish_q.enqueue("workers.tasks.execute_job", str(j.id))
    return j


@router.post("/{job_id}/mark-executed", response_model=JobOut)
def mark_executed(job_id: UUID, platform_ref: str, db: Session = Depends(get_db)):
    """Used by workers (and tests). Enforces the core invariant via the DB CHECK as well."""
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    j.state = "executed"
    j.platform_ref = platform_ref
    j.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(j)
    return j
