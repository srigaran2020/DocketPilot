"""AIBE exam preparation: one row per finished practice set, mock test or speed drill.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "exam_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mode", sa.String(20), nullable=False),  # practice | mock | drill
        sa.Column("subject", sa.String(100)),  # null for a mock test across subjects
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("correct", sa.Integer, nullable=False),
        sa.Column("seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("by_subject", postgresql.JSONB, nullable=False, server_default="{}"),  # subject -> [correct, total]
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exam_attempts")
