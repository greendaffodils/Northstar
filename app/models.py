from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Integer, Float, ForeignKey, JSON, UniqueConstraint, CheckConstraint
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

class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_facility_org_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    region: Mapped[str] = mapped_column(String(100))
    timezone_name: Mapped[str] = mapped_column(String(80), default="UTC")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class EquipmentCategory(Base):
    __tablename__ = "equipment_categories"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_category_org_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")

class Technician(Base):
    __tablename__ = "technicians"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (UniqueConstraint("organization_id", "equipment_tag", name="uq_equipment_org_tag"),
                      CheckConstraint("criticality in ('critical','high','medium','low')", name="ck_equipment_criticality"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("equipment_categories.id"), index=True)
    equipment_tag: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160))
    manufacturer: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(120))
    commissioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    criticality: Mapped[str] = mapped_column(String(20), default="medium")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class FailureEvent(Base):
    __tablename__ = "failure_events"
    __table_args__ = (UniqueConstraint("organization_id", "incident_code", name="uq_failure_org_code"),
                      CheckConstraint("downtime_minutes >= 0", name="ck_failure_downtime_nonnegative"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    incident_code: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    failure_mode: Mapped[str] = mapped_column(String(120))
    root_cause: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    downtime_minutes: Mapped[int] = mapped_column(Integer)
    lost_production_units: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_work_order_idempotency"),
                      CheckConstraint("priority in ('critical','high','normal','low')", name="ck_work_order_priority"),
                      CheckConstraint("status in ('open','in_progress','completed','cancelled','failed')", name="ck_work_order_status"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    failure_event_id: Mapped[str | None] = mapped_column(ForeignKey("failure_events.id"), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    actual_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    technician_id: Mapped[str | None] = mapped_column(ForeignKey("technicians.id"), nullable=True)
    work_order_id: Mapped[str | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    failure_event_id: Mapped[str | None] = mapped_column(ForeignKey("failure_events.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    maintenance_type: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(Text)
    cost: Mapped[float] = mapped_column(Float, default=0)
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)

class SparePart(Base):
    __tablename__ = "spare_parts"
    __table_args__ = (UniqueConstraint("organization_id", "part_number", name="uq_part_org_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    part_number: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)

class EquipmentSparePart(Base):
    __tablename__ = "equipment_spare_parts"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), primary_key=True)
    spare_part_id: Mapped[str] = mapped_column(ForeignKey("spare_parts.id"), primary_key=True)

class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (UniqueConstraint("organization_id", "facility_id", "spare_part_id", name="uq_inventory_location_part"),
                      CheckConstraint("quantity_available >= 0", name="ck_inventory_quantity_nonnegative"),
                      CheckConstraint("reorder_level >= 0", name="ck_inventory_reorder_nonnegative"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    spare_part_id: Mapped[str] = mapped_column(ForeignKey("spare_parts.id"), index=True)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class OperationalMetric(Base):
    __tablename__ = "operational_metrics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metric_name: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30))

class SafetyIncident(Base):
    __tablename__ = "safety_incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    equipment_id: Mapped[str | None] = mapped_column(ForeignKey("equipment.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    lost_time_hours: Mapped[float] = mapped_column(Float, default=0)

class SyntheticDatasetManifest(Base):
    __tablename__ = "synthetic_dataset_manifests"
    __table_args__ = (UniqueConstraint("organization_id", "dataset_name", name="uq_dataset_manifest_org_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String(120))
    generator_version: Mapped[str] = mapped_column(String(30))
    seed: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record_counts: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
