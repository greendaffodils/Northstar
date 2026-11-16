import hashlib
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.security import current_user, require_admin, verify_password, create_token
from app.core.security import hash_password
from app.models import Organization, User, Document, AuditEvent, ActionRequest, IngestionJob, Chunk
from app.services.industrial_analytics import query_industrial
from app.services.action_execution import approve_action, execute_simulated, reject_action as reject_action_service
from app.services.ingestion import ALLOWED
from app.services.retrieval import search
from app.services.answering import answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("enterprise_ai")
DOCUMENT_ROLES = {"admin", "engineer", "analyst", "member", "reader"}

def can_access_document(doc: Document, user: User) -> bool:
    return user.role in {"admin", "owner"} or "*" in doc.allowed_roles \
        or user.role in doc.allowed_roles or user.id in doc.allowed_user_ids

@asynccontextmanager
async def lifespan(app):
    db = SessionLocal()
    try:
        if settings.app_env != "production" and not db.scalar(select(User).limit(1)):
            from app.core.security import hash_password
            org = Organization(id=str(uuid4()), name="Example Organization")
            db.add(org); db.flush()
            db.add(User(id=str(uuid4()), organization_id=org.id, email=settings.bootstrap_email.lower(),
                        password_hash=hash_password(settings.bootstrap_password), role="admin"))
            db.commit()
            log.warning("Created bootstrap administrator for local development")
    finally:
        db.close()
    yield

app = FastAPI(title="Enterprise Knowledge & Action API", version="0.1.0", lifespan=lifespan)

@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

@app.exception_handler(Exception)
async def unhandled(request, exc):
    log.exception("Unhandled error request_id=%s", getattr(request.state, "request_id", "unknown"))
    return JSONResponse(status_code=500, content={"detail": "Internal server error",
                         "request_id": getattr(request.state, "request_id", "unknown")})

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/", response_class=HTMLResponse)
def ui():
    return Path("app/templates/index.html").read_text(encoding="utf-8")

@app.post("/api/auth/token")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": create_token(user), "token_type": "bearer", "role": user.role}

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role, "organization_id": user.organization_id}

class NewUser(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=200)
    role: str = Field(default="member", pattern="^(member|admin|engineer|analyst|reader)$")

@app.post("/api/admin/users", status_code=201)
def create_user(body: NewUser, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email is already registered")
    record = User(id=str(uuid4()), organization_id=user.organization_id, email=email,
                  password_hash=hash_password(body.password), role=body.role)
    db.add(record)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="user.created", details={"user_id": record.id, "role": record.role}))
    db.commit()
    return {"id": record.id, "email": record.email, "role": record.role}

@app.post("/api/documents", status_code=202)
async def upload(file: UploadFile = File(...), access_roles: str = Form(default="inherit"),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() not in ALLOWED:
        raise HTTPException(415, "Supported files: PDF, DOCX, CSV, TXT")
    raw = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File exceeds upload limit")
    from app.services.ingestion import validate_content
    try:
        validate_content(filename, raw)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    digest = hashlib.sha256(raw).hexdigest()
    current = db.scalar(select(Document).where(Document.organization_id == user.organization_id,
        Document.filename == filename, Document.is_current.is_(True), Document.deleted_at.is_(None))
        .order_by(Document.version.desc()).limit(1))
    if current and not can_access_document(current, user):
        raise HTTPException(404, "Document not found")
    inflight = db.scalar(select(Document).where(Document.organization_id == user.organization_id,
        Document.filename == filename, Document.content_hash == digest,
        Document.status.in_(["queued", "processing"]), Document.deleted_at.is_(None))
        .order_by(Document.version.desc()).limit(1))
    if inflight:
        active_job = db.scalar(select(IngestionJob).where(IngestionJob.document_id == inflight.id,
            IngestionJob.status.in_(["queued", "running", "retrying"])).order_by(IngestionJob.created_at.desc()))
        if active_job:
            return {"id": inflight.id, "job_id": active_job.id, "status": inflight.status,
                    "version": inflight.version, "deduplicated": True}
    if current and current.content_hash == digest and current.status in {"queued", "processing", "ready"}:
        active_job = db.scalar(select(IngestionJob).where(IngestionJob.document_id == current.id,
            IngestionJob.status.in_(["queued", "running", "retrying"])).order_by(IngestionJob.created_at.desc()))
        return {"id": current.id, "job_id": active_job.id if active_job else None,
                "status": current.status, "deduplicated": True}
    family_id = current.family_id if current else str(uuid4())
    if access_roles == "inherit" and current:
        roles = list(current.allowed_roles)
        user_ids = list(current.allowed_user_ids)
    else:
        roles = sorted(set(part.strip() for part in access_roles.split(",") if part.strip()))
        user_ids = []
        if not roles or ("*" in roles and len(roles) > 1) or any(role not in DOCUMENT_ROLES | {"*"} for role in roles):
            raise HTTPException(422, "access_roles must be inherit, *, or comma-separated known roles")
        if user.role not in {"admin", "owner"} and "*" not in roles and user.role not in roles:
            raise HTTPException(403, "Uploaded document access must include your role")
    max_version = db.scalar(select(func.max(Document.version)).where(
        Document.organization_id == user.organization_id, Document.family_id == family_id)) or 0
    next_version = max_version + 1
    document_id = str(uuid4())
    path = Path(settings.upload_dir) / user.organization_id / document_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".uploading")
    temp_path.write_bytes(raw)
    temp_path.replace(path)
    doc = Document(id=document_id, organization_id=user.organization_id, family_id=family_id,
                   uploaded_by=user.id, filename=filename, content_hash=digest, version=next_version,
                   is_current=current is None, status="queued", storage_path=str(path),
                   allowed_roles=roles, allowed_user_ids=user_ids)
    job_id = str(uuid4())
    idempotency_key = hashlib.sha256(f"{user.organization_id}:{document_id}:{digest}".encode()).hexdigest()
    job = IngestionJob(id=job_id, organization_id=user.organization_id, document_id=document_id,
                       idempotency_key=idempotency_key, status="queued")
    db.add(doc)
    db.add(job)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="document.uploaded", details={"document_id": doc.id,
                      "filename": doc.filename, "version": doc.version}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(409, "Document upload conflicted; retry the request")
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return {"id": doc.id, "job_id": job.id, "status": doc.status, "version": doc.version,
            "deduplicated": False}

@app.get("/api/documents")
def documents(include_history: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Document).where(Document.organization_id == user.organization_id,
                                   Document.deleted_at.is_(None))
    if not include_history:
        query = query.where(Document.is_current.is_(True))
    docs = [doc for doc in db.scalars(query.order_by(Document.created_at.desc())).all()
            if can_access_document(doc, user)]
    return [{"id": d.id, "family_id": d.family_id, "filename": d.filename, "status": d.status,
             "is_current": d.is_current, "version": d.version,
             "allowed_roles": d.allowed_roles, "allowed_user_count": len(d.allowed_user_ids),
             "error": d.error, "created_at": d.created_at} for d in docs]

@app.get("/api/documents/{document_id}/versions")
def document_versions(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id,
        Document.organization_id == user.organization_id, Document.deleted_at.is_(None)))
    if not doc or not can_access_document(doc, user):
        raise HTTPException(404, "Document not found")
    rows = db.scalars(select(Document).where(Document.organization_id == user.organization_id,
        Document.family_id == doc.family_id, Document.deleted_at.is_(None))
        .order_by(Document.version.desc())).all()
    rows = [item for item in rows if can_access_document(item, user)]
    return [{"id": item.id, "version": item.version, "status": item.status,
             "is_current": item.is_current, "content_hash": item.content_hash,
             "created_at": item.created_at} for item in rows]

class DocumentAccessUpdate(BaseModel):
    allowed_roles: list[str] = Field(min_length=1, max_length=10)
    allowed_user_ids: list[str] = Field(default_factory=list, max_length=100)

@app.put("/api/documents/{document_id}/access")
def update_document_access(document_id: str, body: DocumentAccessUpdate,
                           user: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id,
        Document.organization_id == user.organization_id, Document.deleted_at.is_(None)))
    if not doc:
        raise HTTPException(404, "Document not found")
    roles = sorted(set(body.allowed_roles))
    if ("*" in roles and len(roles) > 1) or any(role not in DOCUMENT_ROLES | {"*"} for role in roles):
        raise HTTPException(422, "Unknown or conflicting document role")
    user_ids = sorted(set(body.allowed_user_ids))
    if user_ids:
        members = set(db.scalars(select(User.id).where(User.organization_id == user.organization_id,
                                                       User.id.in_(user_ids))))
        if members != set(user_ids):
            raise HTTPException(422, "Every allowed user must belong to this organization")
    doc.allowed_roles, doc.allowed_user_ids = roles, user_ids
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="document.access_updated", details={"document_id": doc.id,
        "allowed_roles": roles, "allowed_user_count": len(user_ids)}))
    db.commit()
    return {"id": doc.id, "allowed_roles": doc.allowed_roles,
            "allowed_user_ids": doc.allowed_user_ids}

@app.get("/api/ingestion-jobs/{job_id}")
def ingestion_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id,
        IngestionJob.organization_id == user.organization_id))
    doc = db.get(Document, job.document_id) if job else None
    if not job or not doc or not can_access_document(doc, user):
        raise HTTPException(404, "Ingestion job not found")
    return {"id": job.id, "document_id": job.document_id, "status": job.status,
            "attempts": job.attempts, "progress": job.progress, "last_error": job.last_error,
            "available_at": job.available_at, "created_at": job.created_at, "updated_at": job.updated_at}

@app.post("/api/documents/{document_id}/reindex", status_code=202)
def reindex(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.scalar(select(Document).where(Document.id == document_id,
        Document.organization_id == user.organization_id, Document.deleted_at.is_(None)))
    if not doc or not can_access_document(doc, user):
        raise HTTPException(404, "Document not found")
    if not doc.is_current:
        raise HTTPException(409, "Only the current document version can be reindexed")
    active = db.scalar(select(IngestionJob).where(IngestionJob.document_id == doc.id,
        IngestionJob.status.in_(["queued", "running", "retrying"])).order_by(IngestionJob.created_at.desc()))
    if active:
        return {"id": doc.id, "job_id": active.id, "status": active.status, "deduplicated": True}
    if not Path(doc.storage_path).is_file():
        raise HTTPException(409, "Original file is unavailable; upload the document again")
    job = IngestionJob(id=str(uuid4()), organization_id=user.organization_id, document_id=doc.id,
        idempotency_key=hashlib.sha256(f"reindex:{doc.id}:{uuid4()}".encode()).hexdigest(), status="queued")
    doc.status, doc.error = "queued", None
    db.add(job)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="document.reindex_requested", details={"document_id": doc.id, "job_id": job.id}))
    db.commit()
    return {"id": doc.id, "job_id": job.id, "status": doc.status, "deduplicated": False}

@app.delete("/api/documents/{document_id}", status_code=202)
def delete_document(document_id: str, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if user.role not in {"admin", "owner"}:
        raise HTTPException(403, "Administrator role required to delete documents")
    doc = db.scalar(select(Document).where(Document.id == document_id,
        Document.organization_id == user.organization_id))
    if not doc:
        raise HTTPException(404, "Document not found")
    idempotency_key = hashlib.sha256(f"delete:{user.organization_id}:{doc.family_id}".encode()).hexdigest()
    cleanup_job = db.scalar(select(IngestionJob).where(IngestionJob.idempotency_key == idempotency_key))
    if cleanup_job and cleanup_job.status in {"queued", "running", "retrying", "completed"}:
        return {"status": "deleted", "cleanup_job_id": cleanup_job.id,
                "cleanup_status": cleanup_job.status}
    versions = db.scalars(select(Document).where(Document.organization_id == user.organization_id,
        Document.family_id == doc.family_id).with_for_update()).all()
    ids = [row.id for row in versions]
    paths = [row.storage_path for row in versions if row.storage_path]
    now = datetime.now(timezone.utc)
    for row in versions:
        row.is_current, row.status, row.deleted_at = False, "deleted", now
    db.execute(delete(Chunk).where(Chunk.organization_id == user.organization_id,
                                  Chunk.document_id.in_(ids)))
    db.execute(update(IngestionJob).where(IngestionJob.organization_id == user.organization_id,
        IngestionJob.document_id.in_(ids), IngestionJob.status.in_(["queued", "running", "retrying"]))
        .values(status="cancelled", locked_at=None, updated_at=now))
    if cleanup_job:
        cleanup_job.status, cleanup_job.attempts, cleanup_job.progress = "queued", 0, 0
        cleanup_job.last_error, cleanup_job.locked_at = None, None
        cleanup_job.available_at = now
        cleanup_job.payload = {"document_ids": ids, "storage_paths": paths}
    else:
        cleanup_job = IngestionJob(id=str(uuid4()), organization_id=user.organization_id,
            document_id=ids[0], job_type="delete_vectors",
            idempotency_key=idempotency_key, payload={"document_ids": ids, "storage_paths": paths},
            status="queued")
        db.add(cleanup_job)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="document.deleted", details={"family_id": doc.family_id, "versions": len(ids)}))
    db.commit()
    return {"status": "deleted", "cleanup_job_id": cleanup_job.id,
            "cleanup_status": cleanup_job.status}

class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=12)

@app.post("/api/query")
async def query(body: Ask, user: User = Depends(current_user), db: Session = Depends(get_db)):
    evidence = await run_in_threadpool(search, db, user.organization_id, body.question,
                                       roles=(user.role,), user_id=user.id)
    result = await answer(body.question, evidence, body.history)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="query.completed", details={"question": body.question[:500], "citations": len(result["citations"])}))
    db.commit()
    return {**result, "retrieval": {"strategy": "hybrid_rrf", "results": evidence},
            "workflow": [{"step": "route", "status": "completed", "detail": "Knowledge query routed to hybrid retrieval"},
                         {"step": "retrieve", "status": "completed", "detail": f"Found {len(evidence)} candidate chunks"},
                         {"step": "synthesize", "status": "completed"}]}

class Investigation(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

@app.post("/api/investigations")
async def investigate(body: Investigation, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "owner", "engineer", "analyst"}:
        raise HTTPException(403, "Investigations require analyst, engineer, or administrator access")
    structured = query_industrial(db, user.organization_id, body.question)
    evidence = await run_in_threadpool(search, db, user.organization_id, body.question,
                                       roles=(user.role,), user_id=user.id)
    sources = [{"marker": f"[D{i+1}]", "document_id": item["document_id"],
                "chunk_id": item["chunk_id"], "filename": item["filename"],
                "section": item.get("section"), "text": item["text"]} for i, item in enumerate(evidence)]
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="investigation.completed", details={"question": body.question[:500],
        "intent": structured["intent"], "structured_rows": len(structured["rows"]),
        "document_sources": len(sources)}))
    db.commit()
    return {"question": body.question, "plan": [
                {"step": "structured_analytics", "status": "completed", "intent": structured["intent"]},
                {"step": "document_retrieval", "status": "completed", "source_count": len(sources)}],
            "structured_findings": structured, "document_evidence": sources,
            "validation": {"numeric_claims_synthesized": False,
                           "citations": "Document evidence is individually identified; findings remain in source form."}}

class DataQuery(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    sql: str | None = None

@app.post("/api/data/query")
def data_query(body: DataQuery, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "owner", "engineer", "analyst"}:
        raise HTTPException(403, "Industrial analytics requires analyst, engineer, or administrator access")
    if body.sql is not None:
        raise HTTPException(422, "Raw SQL is not accepted; send a natural-language question in 'question'")
    result = query_industrial(db, user.organization_id, body.question)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="industrial.analytics_queried", details={"intent": result["intent"],
        "question": body.question[:500], "row_count": len(result["rows"])}))
    db.commit()
    return result

class Action(BaseModel):
    kind: str = Field(pattern="^(support_ticket|draft_email|report|work_order)$")
    payload: dict

@app.post("/api/actions", status_code=202)
def request_action(body: Action, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.kind == "work_order":
        if not all(isinstance(body.payload.get(key), str) and body.payload[key].strip()
                   for key in ("equipment_tag", "description")):
            raise HTTPException(422, "work_order payload requires equipment_tag and description")
        if body.payload.get("priority", "normal") not in {"critical", "high", "normal", "low"}:
            raise HTTPException(422, "work_order priority must be critical, high, normal, or low")
        try:
            estimated_cost = float(body.payload.get("estimated_cost", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "estimated_cost must be a non-negative number") from exc
        if not math.isfinite(estimated_cost) or estimated_cost < 0:
            raise HTTPException(422, "estimated_cost must be a non-negative number")
    action = ActionRequest(id=str(uuid4()), organization_id=user.organization_id, requested_by=user.id,
                           kind=body.kind, payload=body.payload, status="pending_approval",
                           idempotency_key=str(uuid4()), execution_result={})
    db.add(action)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="action.requested", details={"action_id": action.id, "kind": body.kind}))
    db.commit()
    return {"id": action.id, "status": action.status,
            "message": "Action recorded for administrator approval; no adapter has run."}

@app.get("/api/actions")
def pending_actions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ActionRequest).where(ActionRequest.organization_id == user.organization_id)
                      .order_by(ActionRequest.created_at.desc())).all()
    return [{"id": a.id, "kind": a.kind, "payload": a.payload, "status": a.status,
             "execution_result": a.execution_result,
             "created_at": a.created_at} for a in rows]

@app.post("/api/actions/{action_id}/approve")
def approve(action_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return approve_action(action_id, user.organization_id, user.id, db)

@app.post("/api/actions/{action_id}/reject")
def reject_action(action_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return reject_action_service(action_id, user.organization_id, user.id, db)

@app.post("/api/actions/{action_id}/execute")
def execute_action(action_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return execute_simulated(action_id, user.organization_id, user.id, db)

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user.organization_id
    count = lambda model, *filters: db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
    return {"documents": count(Document, Document.organization_id == org),
            "indexed_documents": count(Document, Document.organization_id == org, Document.status == "ready"),
            "pending_actions": count(ActionRequest, ActionRequest.organization_id == org, ActionRequest.status == "pending_approval"),
            "queries": count(AuditEvent, AuditEvent.organization_id == org, AuditEvent.event_type == "query.completed")}
