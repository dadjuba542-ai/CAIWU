from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ProcessingJob


def enqueue(db: Session, job_type: str, payload: dict) -> ProcessingJob:
    job = ProcessingJob(job_type=job_type, payload=payload)
    db.add(job); db.commit(); db.refresh(job)
    return job


def claim(db: Session) -> ProcessingJob | None:
    stale = datetime.utcnow() - timedelta(minutes=5)
    stmt = select(ProcessingJob).where(
        ProcessingJob.status.in_(["queued", "running"]),
        (ProcessingJob.locked_at.is_(None)) | (ProcessingJob.heartbeat_at < stale),
    ).order_by(ProcessingJob.created_at).with_for_update(skip_locked=True).limit(1)
    job = db.scalar(stmt)
    if not job:
        return None
    job.status = "running"; job.locked_at = datetime.utcnow(); job.heartbeat_at = datetime.utcnow(); job.attempts += 1
    db.commit(); db.refresh(job)
    return job
