from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def now():
    return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "family_id", "version", name="uq_doc_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    allowed_roles: Mapped[list] = mapped_column(JSON, default=lambda: ["*"])
    allowed_user_ids: Mapped[list] = mapped_column(JSON, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(30), default="ingest")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_vector_ids: Mapped[list] = mapped_column(JSON, default=list)
    payload_updates: Mapped[dict] = mapped_column(JSON, default=dict)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ActionRequest(Base):
    __tablename__ = "action_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    requested_by: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
