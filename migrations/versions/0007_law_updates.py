"""Weekly law update runs: what changed in which Act, failures, and drafts that cite a changed section.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "law_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("acts_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("failed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("affected_drafts", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_table("law_updates")
