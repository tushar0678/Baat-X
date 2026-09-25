"""multi-organization: teams, memberships, invitations, team ownership

Revision ID: 0003_multi_org_teams
Revises: 0002_call_sync_hints
Create Date: 2026-09-24

Matched against the real schema:

  * ``customers.owner_user_id`` already exists - not re-added.
  * ``leads.assigned_user_id`` already exists - ``scope_query`` picks it up,
    so leads need no new ownership column either.
  * Only ``team_id`` is genuinely new.

Additive only: nothing is dropped and no row is deleted. Backfill assumes a
fresh database, but every statement is idempotent and narrowly targeted, so it
is correct even if rows exist.
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

    # ---------------------------------------------------- business_memberships
    op.create_table(
        "business_memberships",
        sa.Column("id", GUID, primary_key=True),
        sa.Column("business_id", GUID, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", GUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False, server_default="member"),
        sa.Column("team_id", GUID, sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("job_title", sa.String(80)),
        sa.Column("granted_permissions", postgresql.JSONB),
        sa.Column("revoked_permissions", postgresql.JSONB),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),
    )
    op.create_index("ix_memberships_user", "business_memberships", ["user_id"])
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

    op.create_index("ix_customers_business_owner", "customers", ["business_id", "owner_user_id"])

    # ------------------------------------------------------------- backfill
    connection = op.get_bind()

    # Every existing user gets a membership, so nobody is locked out.
    connection.execute(
        sa.text(
            """
            INSERT INTO business_memberships (id, business_id, user_id, role, is_active)
            SELECT gen_random_uuid(), b.id, u.id,
                   CASE u.role
                       WHEN 'owner' THEN 'owner'
                       WHEN 'admin' THEN 'manager'
                       ELSE 'member'
                   END,
                   true
            FROM businesses b
            JOIN users u ON u.business_id = b.id
            ON CONFLICT (business_id, user_id) DO NOTHING
            """
        )
    )

    # Guarantee at least one owner per organization.
    connection.execute(
        sa.text(
            """
            UPDATE business_memberships m
            SET role = 'owner'
            WHERE m.id IN (
                SELECT DISTINCT ON (business_id) id
                FROM business_memberships
                WHERE business_id NOT IN (
                    SELECT business_id FROM business_memberships WHERE role = 'owner'
                )
                ORDER BY business_id, joined_at ASC
            )
            """
        )
    )

    # Unowned customers fall to the organization owner rather than becoming
    # invisible to everyone.
    connection.execute(
        sa.text(
            """
            UPDATE customers c
            SET owner_user_id = m.user_id
            FROM business_memberships m
            WHERE c.owner_user_id IS NULL
              AND m.business_id = c.business_id
              AND m.role = 'owner'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_customers_business_owner", table_name="customers")

    for table in ("customers", "leads", "conversation_events", "follow_ups"):
        op.drop_index(f"ix_{table}_team", table_name=table)
        op.drop_column(table, "team_id")

    op.drop_table("invitations")
    op.drop_table("business_memberships")
    op.drop_table("teams")
