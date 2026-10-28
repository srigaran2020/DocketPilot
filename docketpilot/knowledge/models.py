"""Corpus and statute tables (schema agreed in docs/phase0/DATA_REPORT.md Section 7, trimmed for the prototype)."""
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docketpilot.db import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    court: Mapped[str] = mapped_column(String(100), index=True)  # "Supreme Court of India", "Kerala", ...
    court_level: Mapped[str] = mapped_column(String(2))  # SC | HC
    bench: Mapped[str | None] = mapped_column(String(100))
    cnr: Mapped[str | None] = mapped_column(String(40), unique=True)
    case_type: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(Text)
    petitioner: Mapped[str | None] = mapped_column(Text)
    respondent: Mapped[str | None] = mapped_column(Text)
    decision_date: Mapped[date | None] = mapped_column(Date, index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    judges: Mapped[str | None] = mapped_column(Text)
    disposal_nature: Mapped[str | None] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20), default="unknown")
    outcome_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_s138: Mapped[bool] = mapped_column(default=False, index=True)
    has_text: Mapped[bool] = mapped_column(default=False)
    # provenance (spec 5.1)
    source: Mapped[str] = mapped_column(String(100))
    source_key: Mapped[str] = mapped_column(Text)
    licence: Mapped[str] = mapped_column(String(50))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseCitation(Base):
    """Every way a case can be cited. kind: neutral | scr | hc_neutral | alias."""

    __tablename__ = "case_citations"
    __table_args__ = (Index("ix_case_citations_lookup", "kind", "canonical"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    raw: Mapped[str] = mapped_column(Text)
    canonical: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    origin: Mapped[str] = mapped_column(String(20), default="metadata")  # metadata | mined


class Segment(Base):
    """A part of a judgment by role. role 'headnote' is editorial and is never used as evidence."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    ord: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Chunk(Base):
    """Search unit. Full-text index is created in the migration; dense vectors live in Qdrant under this id."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    ord: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class CitationEdge(Base):
    """Case A cites case B. cited_case_id is null when the citation could not be resolved."""

    __tablename__ = "citation_edges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    citing_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    cited_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    raw: Mapped[str] = mapped_column(Text)
    canonical: Mapped[str] = mapped_column(String(120), index=True)
    signal: Mapped[str] = mapped_column(String(20), default="cited")
    sentence: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)


class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    india_code_act_id: Mapped[str] = mapped_column(String(80), unique=True)
    short_name: Mapped[str] = mapped_column(String(40), unique=True)  # "NI Act"
    title: Mapped[str] = mapped_column(Text)
    act_number: Mapped[str | None] = mapped_column(String(20))
    year: Mapped[int | None] = mapped_column(Integer)


class SectionVersion(Base):
    """One version of one section, valid from valid_from (inclusive) to valid_to (exclusive; null = in force).

    status is 'unverified' for everything in the prototype (decision 11).
    """

    __tablename__ = "section_versions"
    __table_args__ = (Index("ix_section_versions_lookup", "act_id", "section_number", "valid_from"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"))
    section_number: Mapped[str] = mapped_column(String(20))
    heading: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    inserted_on: Mapped[date | None] = mapped_column(Date)  # whole section added by amendment on this date
    valid_from: Mapped[date | None] = mapped_column(Date)  # null = from enactment / unknown start
    valid_to: Mapped[date | None] = mapped_column(Date)
    footnotes: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="unverified")


class Amendment(Base):
    """Amendment ledger, parsed from India Code footnotes. Unverified in the prototype."""

    __tablename__ = "amendments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id", ondelete="CASCADE"))
    section_number: Mapped[str] = mapped_column(String(20), index=True)
    note: Mapped[str] = mapped_column(Text)  # footnote text, verbatim
    action: Mapped[str | None] = mapped_column(String(20))  # ins | subs | omitted | added
    amending_act: Mapped[str | None] = mapped_column(String(100))
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="unverified")
