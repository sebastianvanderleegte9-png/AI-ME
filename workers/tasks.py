"""Worker tasks. Every task takes a job id, loads the row, does one thing, records the result.
A task never publishes anything that is not in state approved/edited (Principle 3)."""
from datetime import datetime, timezone
import logging
import uuid

from app.db import SessionLocal
from app.interfaces import get_social
from app.models import Job

log = logging.getLogger("workers")


def heartbeat(job_id: str) -> str:
    """Component 0 done-when: a job moves pending -> executed via the queue."""
    with SessionLocal() as db:
        j = db.get(Job, uuid.UUID(job_id))
        if not j:
            return "missing"
        j.state = "executed"
        j.platform_ref = f"heartbeat-{datetime.now(timezone.utc).isoformat()}"
        j.executed_at = datetime.now(timezone.utc)
        j.output = {"ok": True}
        db.commit()
        log.info("heartbeat executed %s", job_id)
        return "executed"


def execute_job(job_id: str) -> str:
    """Publish an approved/edited job through the Social interface. Component 3 adds
    scheduling (this becomes a scheduled enqueue) and media; the guard stays."""
    with SessionLocal() as db:
        j = db.get(Job, uuid.UUID(job_id))
        if not j:
            return "missing"
        if j.state not in ("approved", "edited"):
            log.warning("refusing to execute job %s in state %s", job_id, j.state)
            return "refused"
        try:
            if j.type in ("post", "reply") and j.channel in ("linkedin", "x"):
                res = get_social().publish(
                    founder_id=str(j.founder_id), channel=j.channel,
                    text=j.output.get("text", ""), media=j.output.get("media"),
                    reply_to_ref=j.input.get("reply_to_ref"))
                j.platform_ref = res.platform_ref
            else:
                # Other job types get their executors in later components.
                j.platform_ref = f"internal-{uuid.uuid4().hex[:8]}"
            j.state = "executed"
            j.executed_at = datetime.now(timezone.utc)
            if j.type == "reply":
                from app.attention.targets import record_reply_executed
                record_reply_executed(db, j)
        except Exception as e:  # noqa: BLE001
            j.state = "failed"
            j.error = str(e)[:2000]
            log.exception("job %s failed", job_id)
        db.commit()
        return j.state


def publish_due() -> int:
    """Safety net for the scheduler: publish any approved/edited job whose slot has passed
    and which is not already executed. Run every few minutes (rq-scheduler or cron)."""
    from sqlalchemy import select
    n = 0
    with SessionLocal() as db:
        due = db.scalars(select(Job).where(Job.state.in_(["approved", "edited"]),
                                           Job.scheduled_for <= datetime.now(timezone.utc))).all()
        ids = [str(j.id) for j in due]
    for jid in ids:
        if execute_job(jid) == "executed":
            n += 1
    return n
