"""add businesses.created_by_user_id and missing column defaults

Revision ID: 0004_business_created_by
Revises: 0003_multi_org_teams
Create Date: 2026-09-26

The ``Business`` model (app/models/tenancy.py) has carried
``created_by_user_id`` since the multi-organization refactor, but no
migration ever added the column to the database - only the Python model was
updated. Separately, ``whatsapp_enabled`` and ``is_active`` were created as
NOT NULL with no server-side default in 0001_initial, and the signup code
never sets them explicitly (they're not exposed on the Business model's
constructor args), so every signup failed with a NOT NULL violation until a
default was patched in manually - twice, after two schema resets. This
migration makes both defaults permanent so a fresh database never regresses.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_business_created_by"
down_revision = "0003_multi_org_teams"
branch_labels = None
depends_on = None

GUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column(
            "created_by_user_id",
            GUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_businesses_created_by",
        "businesses",
        ["created_by_user_id"],
    )

    # These two columns were created NOT NULL with no server default in
    # 0001_initial. The signup endpoint never sets them explicitly, so every
    # fresh database fails signup with a NOT NULL violation until this is
    # patched. Setting the default here makes that permanent.
    op.alter_column(
        "businesses",
        "whatsapp_enabled",
        server_default=sa.false(),
    )
    op.alter_column(
        "businesses",
        "is_active",
        server_default=sa.true(),
    )


def downgrade() -> None:
    op.alter_column("businesses", "is_active", server_default=None)
    op.alter_column("businesses", "whatsapp_enabled", server_default=None)
    op.drop_index("ix_businesses_created_by", table_name="businesses")
    op.drop_column("businesses", "created_by_user_id")