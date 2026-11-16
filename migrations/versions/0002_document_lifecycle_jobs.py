"""Add immutable document versions and persistent ingestion job state."""
from alembic import op
import sqlalchemy as sa

revision = "0002_document_jobs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("uq_doc_org_hash", type_="unique")
        batch.add_column(sa.Column("family_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("storage_path", sa.String(1000), nullable=False, server_default=""))
        batch.add_column(sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("allowed_roles", sa.JSON(), nullable=False, server_default='["*"]'))
        batch.add_column(sa.Column("allowed_user_ids", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE documents SET family_id = id")
    op.execute("UPDATE documents SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("family_id", existing_type=sa.String(36), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_unique_constraint("uq_doc_version", ["organization_id", "family_id", "version"])
        batch.create_index("ix_documents_family_id", ["family_id"])
        batch.create_index("ix_documents_is_current", ["is_current"])

    op.create_table("ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("job_type", sa.String(30), nullable=False, server_default="ingest"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("cleanup_vector_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("payload_updates", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ingestion_jobs_organization_id", "ingestion_jobs", ["organization_id"])
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_available_at", "ingestion_jobs", ["available_at"])

def downgrade():
    op.drop_index("ix_ingestion_jobs_available_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_organization_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_is_current")
        batch.drop_index("ix_documents_family_id")
        batch.drop_constraint("uq_doc_version", type_="unique")
        batch.drop_column("updated_at")
        batch.drop_column("deleted_at")
        batch.drop_column("storage_path")
        batch.drop_column("metadata_json")
        batch.drop_column("allowed_user_ids")
        batch.drop_column("allowed_roles")
        batch.drop_column("is_current")
        batch.drop_column("family_id")
        batch.create_unique_constraint("uq_doc_org_hash", ["organization_id", "content_hash"])
