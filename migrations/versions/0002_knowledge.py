"""Knowledge base: cases, citations, segments, chunks, citation graph, statutes, amendment ledger.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("court", sa.String(100), nullable=False, index=True),
        sa.Column("court_level", sa.String(2), nullable=False),
        sa.Column("bench", sa.String(100)),
        sa.Column("cnr", sa.String(40), unique=True),
        sa.Column("case_type", sa.String(50)),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("petitioner", sa.Text),
        sa.Column("respondent", sa.Text),
        sa.Column("decision_date", sa.Date, index=True),
        sa.Column("year", sa.Integer, index=True),
        sa.Column("judges", sa.Text),
        sa.Column("disposal_nature", sa.String(100)),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("outcome_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_s138", sa.Boolean, nullable=False, server_default=sa.false(), index=True),
        sa.Column("has_text", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_key", sa.Text, nullable=False),
        sa.Column("licence", sa.String(50), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Fuzzy party-name matching for citation resolution (spec 8, Step 3)
    op.execute("CREATE INDEX ix_cases_title_trgm ON cases USING gin (title gin_trgm_ops)")

    op.create_table(
        "case_citations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("raw", sa.Text, nullable=False),
        sa.Column("canonical", sa.String(120), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1"),
        sa.Column("origin", sa.String(20), nullable=False, server_default="metadata"),
    )
    op.create_index("ix_case_citations_lookup", "case_citations", ["kind", "canonical"])

    op.create_table(
        "segments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("segment_id", sa.BigInteger, sa.ForeignKey("segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR, sa.Computed("to_tsvector('english', text)", persisted=True)),
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")

    op.create_table(
        "citation_edges",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("citing_case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("cited_case_id", UUID, sa.ForeignKey("cases.id", ondelete="SET NULL"), index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("raw", sa.Text, nullable=False),
        sa.Column("canonical", sa.String(120), nullable=False, index=True),
        sa.Column("signal", sa.String(20), nullable=False, server_default="cited"),
        sa.Column("sentence", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
    )

    op.create_table(
        "acts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("india_code_act_id", sa.String(80), nullable=False, unique=True),
        sa.Column("short_name", sa.String(40), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("act_number", sa.String(20)),
        sa.Column("year", sa.Integer),
    )
    op.create_table(
        "section_versions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("act_id", sa.Integer, sa.ForeignKey("acts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_number", sa.String(20), nullable=False),
        sa.Column("heading", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("inserted_on", sa.Date),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_to", sa.Date),
        sa.Column("footnotes", sa.Text, nullable=False, server_default=""),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unverified"),
    )
    op.create_index("ix_section_versions_lookup", "section_versions", ["act_id", "section_number", "valid_from"])
    op.create_table(
        "amendments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("act_id", sa.Integer, sa.ForeignKey("acts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_number", sa.String(20), nullable=False, index=True),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("action", sa.String(20)),
        sa.Column("amending_act", sa.String(100)),
        sa.Column("effective_date", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="unverified"),
    )


def downgrade() -> None:
    for t in ("amendments", "section_versions", "acts", "citation_edges", "chunks", "segments",
              "case_citations", "cases"):
        op.drop_table(t)
