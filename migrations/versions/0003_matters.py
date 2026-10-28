"""Matters, redacted documents, drafts (with verification reports), reminders.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "matters",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("firm_id", UUID, sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),  # lawyer's own label; should not hold client names
        sa.Column("court", sa.String(200)),
        sa.Column("case_number", sa.String(100)),
        sa.Column("stage", sa.String(50), nullable=False, server_default="pre-notice"),
        sa.Column("facts", JSONB, nullable=False, server_default="{}"),  # redacted, placeholders only
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "matter_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("pages", sa.Integer, nullable=False, server_default="1"),
        sa.Column("text_source", sa.String(20), nullable=False),  # text_layer | plain_text | docx
        sa.Column("redacted_text", sa.Text, nullable=False),
        sa.Column("masks", JSONB, nullable=False, server_default="[]"),  # [{type, placeholder, start, end}], no values
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "drafts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("template", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),  # awaiting_approval | blocked | approved | failed
        sa.Column("thread_id", sa.String(100), nullable=False),  # LangGraph checkpoint thread
        sa.Column("redacted_text", sa.Text),
        sa.Column("verification", JSONB),
        sa.Column("checklist", JSONB),
        sa.Column("similar_cases", JSONB),
        sa.Column("research", JSONB),
        sa.Column("trace", JSONB, nullable=False, server_default="[]"),
        sa.Column("acknowledged", JSONB, nullable=False, server_default="[]"),
        sa.Column("output_file", sa.Text),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("matter_id", "version"),
    )
    op.create_table(
        "reminders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rule_id", sa.String(50)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False, index=True),
        sa.Column("warn_on", sa.Date),
        sa.Column("source", sa.Text, nullable=False),  # statute reference behind the date
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("matter_id", "rule_id"),
    )


def downgrade() -> None:
    for t in ("reminders", "drafts", "matter_documents", "matters"):
        op.drop_table(t)
