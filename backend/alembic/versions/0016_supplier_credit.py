"""supplier credit: ledger entries for goods bought on credit

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-28 10:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "ledger_entries", type_="check")
    op.create_check_constraint(
        "kind", "ledger_entries", "kind in ('money','credit_given','credit_taken')"
    )


def downgrade() -> None:
    op.execute("UPDATE ledger_entries SET kind = 'money' WHERE kind = 'credit_taken'")
    op.drop_constraint("kind", "ledger_entries", type_="check")
    op.create_check_constraint("kind", "ledger_entries", "kind in ('money','credit_given')")
