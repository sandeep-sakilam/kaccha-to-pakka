"""audit log append-only trigger

Revision ID: 0002
Revises: 0001
"""

from alembic import op
from app.db.triggers import AUDIT_APPEND_ONLY

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(AUDIT_APPEND_ONLY)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
