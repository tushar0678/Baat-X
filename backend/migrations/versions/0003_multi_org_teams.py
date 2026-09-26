"""multi-organization: teams, membership columns, invitations, team ownership

Revision ID: 0003_multi_org_teams
Revises: 0002_call_sync_hints
Create Date: 2026-09-24

IMPORTANT - corrected against 0001_initial.py:

  0001_initial already creates ``business_memberships`` with a basic shape:
  ``id, business_id, user_id, role, is_active, created_at, updated_at``.
  The original version of this migration tried to ``create_table`` it again,
  which always failed with DuplicateTableError - deterministically, on every
  fresh database, not as a race condition. This version instead ADDS the
  columns this migration actually needs on top of the existing table:
  ``team_id, job_title, granted_permissions, revoked_permissions, joined_at``.

Also matched against the real schema:
  * ``customers.owner_user_id`` already exists - not re-added.
  * ``leads.assigned_user_id`` already exists - ``scope_query`` picks it up,
    so leads need no new ownership column either.
  * Only ``team_id`` is genuinely new on customers/leads/conversation_events/
    follow_ups.

Additive only: nothing is dropped and no row is deleted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_multi_org_teams"
down_revision = "0002_call_sync_hints"
branch_labels = None
depends_on = None

GUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # ---------------------------------------------------------------- teams
    op.create_table(
        "teams",
        sa.Column("id", GUID, primary_key=True),
        sa.Column("business_id", GUID, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400)),
        sa.Column("lead_user_id", GUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("parent_team_id", GUID, sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("business_id", "name", name="uq_team_business_name"),
    )
    op.create_index("ix_teams_business", "teams", ["business_id"])
    op.create_index("ix_teams_lead", "teams", ["lead_user_id"])
    op.create_index("ix_teams_parent", "teams", ["parent_team_id"])

    # ------------------------------------------- business_memberships (ALTER, not CREATE)
    # Table already exists from 0001_initial with:
    #   id, business_id, user_id, role, is_active, created_at, updated_at
    # and a unique constraint uq_membership_business_user(business_id, user_id).
    # We only add what the multi-org / team-hierarchy feature needs.
    op.add_column(
        "business_memberships",
        sa.Column("team_id", GUID, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "business_memberships",
        sa.Column("job_title", sa.String(80), nullable=True),
    )
    op.add_column(
        "business_memberships",
        sa.Column("granted_permissions", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "business_memberships",
        sa.Column("revoked_permissions", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "business_memberships",
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_memberships_business_team", "business_memberships", ["business_id", "team_id"])

    # ---------------------------------------------------------- invitations
    op.create_table(
        "invitations",
        sa.Column("id", GUID, primary_key=True),
        sa.Column("business_id", GUID, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(32)),
        sa.Column("role", sa.String(24), nullable=False, server_default="member"),
        sa.Column("team_id", GUID, sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("job_title", sa.String(80)),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by_user_id", GUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("accepted_by_user_id", GUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)
    op.create_index("ix_invitations_business_status", "invitations", ["business_id", "status"])
    op.create_index("ix_invitations_email", "invitations", ["email"])

    # ------------------------------------------------- team ownership columns
    for table in ("customers", "leads", "conversation_events", "follow_ups"):
        op.add_column(table, sa.Column("team_id", GUID, nullable=True))
        op.create_index(f"ix_{table}_team", table, ["team_id"])

    op.create_index(
        "ix_customers_business_owner", "customers", ["business_id", "owner_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_customers_business_owner", table_name="customers")

    for table in ("customers", "leads", "conversation_events", "follow_ups"):
        op.drop_index(f"ix_{table}_team", table_name=table)
        op.drop_column(table, "team_id")

    op.drop_table("invitations")

    op.drop_index("ix_memberships_business_team", table_name="business_memberships")
    op.drop_column("business_memberships", "joined_at")
    op.drop_column("business_memberships", "revoked_permissions")
    op.drop_column("business_memberships", "granted_permissions")
    op.drop_column("business_memberships", "job_title")
    op.drop_column("business_memberships", "team_id")

    op.drop_table("teams")
