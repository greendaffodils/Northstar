import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine, get_db
from app.core.security import current_user, require_admin, verify_password, create_token
from app.core.security import hash_password
from app.models import Organization, User, Document, AuditEvent, ActionRequest
from app.services.ingestion import ingest, ALLOWED
from app.services.retrieval import search
from app.services.answering import answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("enterprise_ai")

@asynccontextmanager
async def lifespan(app):
    if settings.app_env != "production":
        Base.metadata.create_all(engine)
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
    role: str = Field(default="member", pattern="^(member|admin)$")

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
async def upload(background: BackgroundTasks, file: UploadFile = File(...),
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
    existing = db.scalar(select(Document).where(Document.organization_id == user.organization_id,
                                                Document.content_hash == digest))
    if existing:
        return {"id": existing.id, "status": existing.status, "deduplicated": True}
    doc = Document(id=str(uuid4()), organization_id=user.organization_id, uploaded_by=user.id,
                   filename=filename, content_hash=digest, status="queued")
    path = Path(settings.upload_dir) / user.organization_id / doc.id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".uploading")
    temp_path.write_bytes(raw)
    temp_path.replace(path)
    db.add(doc)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="document.uploaded", details={"document_id": doc.id, "filename": doc.filename}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        existing = db.scalar(select(Document).where(Document.organization_id == user.organization_id,
                                                    Document.content_hash == digest))
        if existing:
            return {"id": existing.id, "status": existing.status, "deduplicated": True}
        raise HTTPException(409, "Document upload conflicted; retry the request")
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    background.add_task(ingest, doc.id, raw)
    return {"id": doc.id, "status": doc.status, "deduplicated": False}

@app.get("/api/documents")
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).where(Document.organization_id == user.organization_id)
                      .order_by(Document.created_at.desc())).all()
    return [{"id": d.id, "filename": d.filename, "status": d.status, "version": d.version,
             "error": d.error, "created_at": d.created_at} for d in docs]

class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=12)

@app.post("/api/query")
async def query(body: Ask, user: User = Depends(current_user), db: Session = Depends(get_db)):
    evidence = await run_in_threadpool(search, db, user.organization_id, body.question)
    result = await answer(body.question, evidence, body.history)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
        event_type="query.completed", details={"question": body.question[:500], "citations": len(result["citations"])}))
    db.commit()
    return {**result, "retrieval": {"strategy": "hybrid_rrf", "results": evidence},
            "workflow": [{"step": "route", "status": "completed", "detail": "Knowledge query routed to hybrid retrieval"},
                         {"step": "retrieve", "status": "completed", "detail": f"Found {len(evidence)} candidate chunks"},
                         {"step": "synthesize", "status": "completed"}]}

class SqlRequest(BaseModel):
    sql: str = Field(min_length=8, max_length=4000)

@app.post("/api/data/query", status_code=503)
def data_query(body: SqlRequest, user: User = Depends(current_user)):
    # The former regex-only SQL executor had no tenant-aware industrial schema or DB-level
    # read-only role. Keep the route discoverable, but do not execute user-supplied SQL.
    raise HTTPException(503, "Structured data queries are temporarily unavailable pending safe schema-aware execution")

class Action(BaseModel):
    kind: str = Field(pattern="^(support_ticket|draft_email|report)$")
    payload: dict

@app.post("/api/actions", status_code=202)
def request_action(body: Action, user: User = Depends(current_user), db: Session = Depends(get_db)):
    action = ActionRequest(id=str(uuid4()), organization_id=user.organization_id, requested_by=user.id,
                           kind=body.kind, payload=body.payload, status="pending_approval")
    db.add(action)
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="action.requested", details={"action_id": action.id, "kind": body.kind}))
    db.commit()
    return {"id": action.id, "status": action.status,
            "message": "Action recorded for administrator approval; no external side effect was performed."}

@app.get("/api/actions")
def pending_actions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ActionRequest).where(ActionRequest.organization_id == user.organization_id)
                      .order_by(ActionRequest.created_at.desc())).all()
    return [{"id": a.id, "kind": a.kind, "payload": a.payload, "status": a.status,
             "created_at": a.created_at} for a in rows]

@app.post("/api/actions/{action_id}/approve")
def approve(action_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    action = db.scalar(select(ActionRequest).where(ActionRequest.id == action_id,
                                                    ActionRequest.organization_id == user.organization_id))
    if not action:
        raise HTTPException(404, "Action not found")
    if action.status != "pending_approval":
        raise HTTPException(409, "Action is not pending")
    action.status = "approved"
    db.add(AuditEvent(id=str(uuid4()), organization_id=user.organization_id, actor_id=user.id,
                      event_type="action.approved", details={"action_id": action.id}))
    db.commit()
    return {"id": action.id, "status": action.status,
            "message": "Approved. Connect a reviewed tool adapter to execute this action."}

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user.organization_id
    count = lambda model, *filters: db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
    return {"documents": count(Document, Document.organization_id == org),
            "indexed_documents": count(Document, Document.organization_id == org, Document.status == "ready"),
            "pending_actions": count(ActionRequest, ActionRequest.organization_id == org, ActionRequest.status == "pending_approval"),
            "queries": count(AuditEvent, AuditEvent.organization_id == org, AuditEvent.event_type == "query.completed")}
