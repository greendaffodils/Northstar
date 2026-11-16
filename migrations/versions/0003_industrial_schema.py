"""Create tenant-scoped synthetic industrial operations tables."""
from alembic import op
import sqlalchemy as sa

revision = "0003_industrial"
down_revision = "0002_document_jobs"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("facilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("region", sa.String(100), nullable=False),
        sa.Column("timezone_name", sa.String(80), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_facility_org_name"))
    op.create_index("ix_facilities_organization_id", "facilities", ["organization_id"])
    op.create_table("equipment_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_category_org_name"))
    op.create_index("ix_equipment_categories_organization_id", "equipment_categories", ["organization_id"])
    op.create_table("technicians",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False), sa.Column("trade", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False))
    op.create_index("ix_technicians_organization_id", "technicians", ["organization_id"])
    op.create_index("ix_technicians_facility_id", "technicians", ["facility_id"])
    op.create_table("equipment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("equipment_categories.id"), nullable=False),
        sa.Column("equipment_tag", sa.String(40), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False), sa.Column("model", sa.String(120), nullable=False),
        sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criticality", sa.String(20), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "equipment_tag", name="uq_equipment_org_tag"),
        sa.CheckConstraint("criticality in ('critical','high','medium','low')", name="ck_equipment_criticality"))
    for column in ("organization_id", "facility_id", "category_id", "equipment_tag"):
        op.create_index(f"ix_equipment_{column}", "equipment", [column])
    op.create_table("failure_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("incident_code", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_mode", sa.String(120), nullable=False), sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False), sa.Column("downtime_minutes", sa.Integer(), nullable=False),
        sa.Column("lost_production_units", sa.Integer(), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "incident_code", name="uq_failure_org_code"),
        sa.CheckConstraint("downtime_minutes >= 0", name="ck_failure_downtime_nonnegative"))
    for column in ("organization_id", "equipment_id", "occurred_at"):
        op.create_index(f"ix_failure_events_{column}", "failure_events", [column])
    op.create_table("work_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("failure_event_id", sa.String(36), sa.ForeignKey("failure_events.id")),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False), sa.Column("actual_cost", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_work_order_idempotency"),
        sa.CheckConstraint("priority in ('critical','high','normal','low')", name="ck_work_order_priority"),
        sa.CheckConstraint("status in ('open','in_progress','completed','cancelled','failed')", name="ck_work_order_status"))
    for column in ("organization_id", "equipment_id", "status", "created_at"):
        op.create_index(f"ix_work_orders_{column}", "work_orders", [column])
    op.create_table("maintenance_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("technician_id", sa.String(36), sa.ForeignKey("technicians.id")),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id")),
        sa.Column("failure_event_id", sa.String(36), sa.ForeignKey("failure_events.id")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maintenance_type", sa.String(50), nullable=False), sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False), sa.Column("downtime_minutes", sa.Integer(), nullable=False))
    for column in ("organization_id", "equipment_id", "occurred_at"):
        op.create_index(f"ix_maintenance_logs_{column}", "maintenance_logs", [column])
    op.create_table("spare_parts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("part_number", sa.String(60), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("unit_cost", sa.Float(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", "part_number", name="uq_part_org_number"))
    op.create_index("ix_spare_parts_organization_id", "spare_parts", ["organization_id"])
    op.create_index("ix_spare_parts_part_number", "spare_parts", ["part_number"])
    op.create_table("equipment_spare_parts",
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id"), primary_key=True),
        sa.Column("spare_part_id", sa.String(36), sa.ForeignKey("spare_parts.id"), primary_key=True))
    op.create_table("inventory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("spare_part_id", sa.String(36), sa.ForeignKey("spare_parts.id"), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False), sa.Column("reorder_level", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "facility_id", "spare_part_id", name="uq_inventory_location_part"),
        sa.CheckConstraint("quantity_available >= 0", name="ck_inventory_quantity_nonnegative"),
        sa.CheckConstraint("reorder_level >= 0", name="ck_inventory_reorder_nonnegative"))
    for column in ("organization_id", "facility_id", "spare_part_id"):
        op.create_index(f"ix_inventory_{column}", "inventory", [column])
    op.create_table("operational_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(80), nullable=False), sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False))
    for column in ("organization_id", "equipment_id", "measured_at", "metric_name"):
        op.create_index(f"ix_operational_metrics_{column}", "operational_metrics", [column])
    op.create_table("safety_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("equipment_id", sa.String(36), sa.ForeignKey("equipment.id")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("corrective_action", sa.Text(), nullable=False),
        sa.Column("lost_time_hours", sa.Float(), nullable=False))
    for column in ("organization_id", "facility_id", "occurred_at"):
        op.create_index(f"ix_safety_incidents_{column}", "safety_incidents", [column])
    op.create_table("synthetic_dataset_manifests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("dataset_name", sa.String(120), nullable=False),
        sa.Column("generator_version", sa.String(30), nullable=False), sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_counts", sa.JSON(), nullable=False), sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "dataset_name", name="uq_dataset_manifest_org_name"))
    op.create_index("ix_synthetic_dataset_manifests_organization_id", "synthetic_dataset_manifests", ["organization_id"])

def downgrade():
    op.drop_index("ix_synthetic_dataset_manifests_organization_id", table_name="synthetic_dataset_manifests")
    op.drop_table("synthetic_dataset_manifests")
    for table, columns in [
        ("safety_incidents", ["occurred_at", "facility_id", "organization_id"]),
        ("operational_metrics", ["metric_name", "measured_at", "equipment_id", "organization_id"]),
        ("inventory", ["spare_part_id", "facility_id", "organization_id"]),
        ("spare_parts", ["part_number", "organization_id"]),
        ("maintenance_logs", ["occurred_at", "equipment_id", "organization_id"]),
        ("work_orders", ["created_at", "status", "equipment_id", "organization_id"]),
        ("failure_events", ["occurred_at", "equipment_id", "organization_id"]),
        ("equipment", ["equipment_tag", "category_id", "facility_id", "organization_id"]),
        ("technicians", ["facility_id", "organization_id"]),
        ("equipment_categories", ["organization_id"]), ("facilities", ["organization_id"]),
    ]:
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
    for table in ("safety_incidents", "operational_metrics", "inventory", "equipment_spare_parts",
                  "spare_parts", "maintenance_logs", "work_orders", "failure_events", "equipment",
                  "technicians", "equipment_categories", "facilities"):
        op.drop_table(table)
