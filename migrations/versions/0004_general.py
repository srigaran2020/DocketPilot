"""General-purpose drafting and statute search: drafts record what was asked for; statute text gets a search index.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATUTE_TSV = "to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(text, ''))"


def upgrade() -> None:
    op.add_column("drafts", sa.Column("doc_type", sa.String(200)))  # "Bail application", "Divorce petition", ...
    op.add_column("drafts", sa.Column("instructions", sa.Text))  # the lawyer's request, redacted
    op.alter_column("drafts", "template", type_=sa.String(60))
    op.execute(f"CREATE INDEX ix_section_versions_tsv ON section_versions USING gin ({STATUTE_TSV})")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_section_versions_tsv")
    op.drop_column("drafts", "instructions")
    op.drop_column("drafts", "doc_type")
