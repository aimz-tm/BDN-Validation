"""widen transactions classification check constraint

Revision ID: 202608150001
Revises: 202605230001
Create Date: 2026-08-15 22:28:56.515879

The check constraint only allowed ('VALID', 'SUSPICIOUS', 'HIGH_RISK'), but
the application has produced REVIEW_REQUIRED since scoring_service/scorer.py
was written, and PUT /transactions/{id} (review approve/reject) has always
written REJECTED and MANUALLY_APPROVED. Every reject action, and any
REVIEW_REQUIRED verdict, was silently rejected by Postgres and swallowed by
the caller's try/except — the app looked like it worked (200 OK) but the
review decision never actually persisted.
"""
from alembic import op
import sqlalchemy as sa


revision = "202608150001"
down_revision = "202605230001"
branch_labels = None
depends_on = None

_OLD_VALUES = "('VALID', 'SUSPICIOUS', 'HIGH_RISK')"
_NEW_VALUES = "('VALID', 'SUSPICIOUS', 'HIGH_RISK', 'REVIEW_REQUIRED', 'REJECTED', 'MANUALLY_APPROVED')"


def upgrade() -> None:
    op.drop_constraint("ck_transactions_classification", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transactions_classification",
        "transactions",
        f"classification IS NULL OR classification IN {_NEW_VALUES}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_transactions_classification", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transactions_classification",
        "transactions",
        f"classification IS NULL OR classification IN {_OLD_VALUES}",
    )
