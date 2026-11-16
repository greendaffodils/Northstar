from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Chunk, Document, IngestionJob, Organization
from app import worker
import app.services.ingestion as ingestion
import app.services.retrieval as retrieval
from app.services.retrieval import eligible_chunks


@pytest.fixture
def worker_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(ingestion, "SessionLocal", factory)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_job(factory, tmp_path, *, version=1, is_current=True, prior=None, existing_chunks=()):
    db = factory()
    org = Organization(id="org-1", name="Synthetic Plant")
    db.add(org)
    if prior:
        db.add(prior)
        db.flush()
    path = tmp_path / f"doc-v{version}.txt"
    path.write_text("Motor bearing temperature exceeded operating range. " * 50, encoding="utf-8")
    doc = Document(id=f"doc-{version}", organization_id="org-1", family_id="family-1",
                   uploaded_by="operator-1", filename="motor-maintenance.txt",
                   content_hash=str(version) * 64, version=version, is_current=is_current,
                   status="queued", storage_path=str(path))
    db.add(doc)
    for chunk_id in existing_chunks:
        db.add(Chunk(id=chunk_id, document_id=prior.id, organization_id="org-1", ordinal=0,
                     text="Older maintenance evidence", metadata_json={"filename": prior.filename}))
    job = IngestionJob(id=f"job-{version}", organization_id="org-1", document_id=doc.id,
                       idempotency_key=f"key-{version}", status="queued")
    db.add(job)
    db.commit()
    db.close()
    return doc.id


def test_worker_claims_and_completes_persisted_ingestion(worker_db, tmp_path, monkeypatch):
    _seed_job(worker_db, tmp_path)
    monkeypatch.setattr(retrieval, "embed_and_upsert", lambda *_args: None)
    monkeypatch.setattr(retrieval, "delete_vectors", lambda *_args: None)
    monkeypatch.setattr(retrieval, "set_document_current", lambda *_args: None)

    job_id = worker.claim_job()
    assert job_id == "job-1"
    ingestion.process_job(job_id)

    db = worker_db()
    job = db.get(IngestionJob, job_id)
    doc = db.get(Document, "doc-1")
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == "doc-1")))
    assert job.status == "completed"
    assert job.progress == 100
    assert doc.status == "ready" and doc.is_current
    assert len(chunks) > 1
    db.close()


def test_new_version_replaces_current_only_after_success(worker_db, tmp_path, monkeypatch):
    prior = Document(id="doc-1", organization_id="org-1", family_id="family-1",
                     uploaded_by="operator-1", filename="motor-maintenance.txt",
                     content_hash="1" * 64, version=1, is_current=True, status="ready",
                     storage_path=str(tmp_path / "old.txt"))
    (tmp_path / "old.txt").write_text("Old manual content", encoding="utf-8")
    _seed_job(worker_db, tmp_path, version=2, is_current=False, prior=prior,
              existing_chunks=["old-vector-id"])
    deleted = []
    monkeypatch.setattr(retrieval, "embed_and_upsert", lambda *_args: None)
    monkeypatch.setattr(retrieval, "delete_vectors", lambda ids: deleted.extend(ids))
    monkeypatch.setattr(retrieval, "set_document_current", lambda *_args: None)

    job_id = worker.claim_job()
    ingestion.process_job(job_id)

    db = worker_db()
    old = db.get(Document, "doc-1")
    new = db.get(Document, "doc-2")
    assert old.status == "superseded" and not old.is_current
    assert new.status == "ready" and new.is_current
    assert "old-vector-id" not in deleted  # preserved for later historical retrieval
    db.close()


def test_claim_recovers_stale_running_job(worker_db, tmp_path):
    _seed_job(worker_db, tmp_path)
    db = worker_db()
    job = db.get(IngestionJob, "job-1")
    job.status = "running"
    job.attempts = 1
    job.locked_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    db.close()

    assert worker.claim_job() == "job-1"
    db = worker_db()
    job = db.get(IngestionJob, "job-1")
    assert job.status == "running" and job.attempts == 2
    db.close()


def test_failed_ingestion_is_retried_with_persisted_error(worker_db, tmp_path):
    _seed_job(worker_db, tmp_path)
    (tmp_path / "doc-v1.txt").unlink()
    job_id = worker.claim_job()
    ingestion.process_job(job_id)
    db = worker_db()
    job = db.get(IngestionJob, job_id)
    doc = db.get(Document, "doc-1")
    assert job.status == "retrying"
    assert job.attempts == 1
    assert "No such file" in job.last_error
    assert doc.status == "queued"
    db.close()


def test_retrieval_eligibility_excludes_old_deleted_and_other_tenant(worker_db):
    db = worker_db()
    db.add_all([Organization(id="org-1", name="A"), Organization(id="org-2", name="B")])
    docs = [
        Document(id="current", organization_id="org-1", family_id="f1", uploaded_by="u",
                 filename="current.txt", content_hash="a", version=2, is_current=True,
                 status="ready", storage_path="current.txt", allowed_roles=["member"]),
        Document(id="old", organization_id="org-1", family_id="f1", uploaded_by="u",
                 filename="old.txt", content_hash="b", version=1, is_current=False,
                 status="superseded", storage_path="old.txt"),
        Document(id="deleted", organization_id="org-1", family_id="f2", uploaded_by="u",
                 filename="deleted.txt", content_hash="c", version=1, is_current=False,
                 status="deleted", storage_path="deleted.txt", deleted_at=datetime.now(timezone.utc)),
        Document(id="tenant-b", organization_id="org-2", family_id="f3", uploaded_by="v",
                 filename="tenant-b.txt", content_hash="d", version=1, is_current=True,
                 status="ready", storage_path="tenant-b.txt"),
    ]
    db.add_all(docs)
    db.flush()
    db.add_all([Chunk(id=f"chunk-{doc.id}", document_id=doc.id, organization_id=doc.organization_id,
                      ordinal=0, text=doc.filename, metadata_json={}) for doc in docs])
    db.commit()

    rows = eligible_chunks(db, "org-1", roles=("member",), user_id="member-1")
    assert [row.document_id for row in rows] == ["current"]
    assert eligible_chunks(db, "org-1", roles=("analyst",), user_id="analyst-1") == []
    db.close()
