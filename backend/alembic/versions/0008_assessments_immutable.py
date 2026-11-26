"""assessments immutable trigger

Revision ID: 0008
Revises: 0007
"""

from alembic import op
from app.db.triggers import ASSESSMENT_IMMUTABLE

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(ASSESSMENT_IMMUTABLE)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS assessments_no_change ON assessments")
    op.execute("DROP FUNCTION IF EXISTS assessments_immutable()")
