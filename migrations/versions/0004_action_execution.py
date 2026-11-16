"""Add idempotent action execution state."""
from alembic import op
import sqlalchemy as sa

revision = "0004_action_execution"
down_revision = "0003_industrial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("action_requests", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("action_requests", sa.Column("execution_result", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_action_requests_idempotency_key", "action_requests", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("ix_action_requests_idempotency_key", table_name="action_requests")
    op.drop_column("action_requests", "execution_result")
    op.drop_column("action_requests", "idempotency_key")
