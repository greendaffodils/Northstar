"""Local durable polling worker for ingestion jobs."""
import logging
import json
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, select
from app.core.db import SessionLocal
from app.models import IngestionJob
from app.services.ingestion import process_job
from app.core.telemetry import tracer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("northstar.worker")
stop = threading.Event()
worker_tracer = tracer("northstar.worker")

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
            started = time.perf_counter()
            with worker_tracer.start_as_current_span("ingestion.process") as span:
                if span:
                    span.set_attribute("job.id", job_id)
                process_job(job_id)
            db = SessionLocal()
            try:
                job = db.get(IngestionJob, job_id)
                status = job.status if job else "missing"
            finally:
                db.close()
            log.info(json.dumps({"event": "ingestion.job_finished", "job_id": job_id,
                "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}))
        else:
            stop.wait(1.5)
    log.info("Ingestion worker stopped")

if __name__ == "__main__":
    main()
