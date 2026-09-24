"""add hinted_name to ai_processing_jobs (call sync)

Revision ID: 0002_call_sync_hints
Revises: 0001_initial
Create Date: 2026-09-24

Additive only. Lets the Android client attach the contact name it already knows
for a call it just finished, so the CRM record shows a name even when the
conversation itself never says one. The phone number - which is the actual
identity key - already had a column.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_call_sync_hints"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_processing_jobs",
        sa.Column("hinted_name", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_jobs_business_hinted_phone",
        "ai_processing_jobs",
        ["business_id", "hinted_phone"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_business_hinted_phone", table_name="ai_processing_jobs")
    op.drop_column("ai_processing_jobs", "hinted_name")
