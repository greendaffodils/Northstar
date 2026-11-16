"""Local durable polling worker for ingestion jobs."""
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, select
from app.core.db import SessionLocal
from app.models import IngestionJob
from app.services.ingestion import process_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("northstar.worker")
stop = threading.Event()

def claim_job() -> str | None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(hours=1)
        available = or_(
            IngestionJob.status == "queued",
            and_(IngestionJob.status == "retrying", IngestionJob.available_at <= now),
            and_(IngestionJob.status == "running", IngestionJob.locked_at < stale_before),
        )
        job = db.scalar(select(IngestionJob).where(available)
                        .order_by(IngestionJob.available_at, IngestionJob.created_at)
                        .with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_at = now
        db.commit()
        return job.id
    except Exception:
        db.rollback()
        log.exception("Could not claim ingestion job")
        return None
    finally:
        db.close()

def request_stop(_signum, _frame):
    stop.set()

def main():
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    log.info("Ingestion worker started")
    while not stop.is_set():
        job_id = claim_job()
        if job_id:
            log.info("Processing ingestion job_id=%s", job_id)
            process_job(job_id)
        else:
            stop.wait(1.5)
    log.info("Ingestion worker stopped")

if __name__ == "__main__":
    main()
