"""Persistence models. Audit events are append-only (enforced below)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


def utcnow() -> datetime: return datetime.now(timezone.utc)
def new_id(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("app"))
    company_name: Mapped[str] = mapped_column(String(200))
    entity_id: Mapped[str] = mapped_column(String(80))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    reporting_period: Mapped[str] = mapped_column(String(40))
    scenario_key: Mapped[Optional[str]] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(30), default="not_assessed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    documents: Mapped[list["Document"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="application", cascade="all, delete-orphan")


class Document(Base):
    """Stable identity across revisions."""
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("doc"))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[Optional[str]] = mapped_column(String(60))   # graph node id, e.g. doc_bank
    doc_type: Mapped[str] = mapped_column(String(30), default="unknown")
    type_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[Application] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"), Index("ix_dv_hash", "file_hash"))
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("dv"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64))            # SHA-256 hex
    storage_path: Mapped[Optional[str]] = mapped_column(String(500))  # None for demo fixtures
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processing_status: Mapped[str] = mapped_column(String(30), default="uploaded")
    verification_status: Mapped[str] = mapped_column(String(30), default="pending_review")
    reporting_period: Mapped[Optional[str]] = mapped_column(String(40))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    extraction_mode: Mapped[Optional[str]] = mapped_column(String(30))
    extracted_pages: Mapped[Optional[Any]] = mapped_column(JSON)  # [{page, text, tables, blocks:[{bbox,text}]}]
    diagnostics: Mapped[list] = mapped_column(JSON, default=list)
    document: Mapped[Document] = relationship(back_populates="versions")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_app_node", "application_id", "node_id"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("clm"))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(80))
    node_id: Mapped[str] = mapped_column(String(60))               # graph node this claim feeds
    claim_type: Mapped[str] = mapped_column(String(60))
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))   # NULL = unavailable, never 0
    currency: Mapped[str] = mapped_column(String(3))
    unit: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)    # NULL = provenance unavailable
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text)
    bbox: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    extraction_mode: Mapped[str] = mapped_column(String(30))
    verification_status: Mapped[str] = mapped_column(String(30), default="pending_review")
    supersedes_claim_id: Mapped[Optional[str]] = mapped_column(ForeignKey("claims.id"))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)  # old versions' claims stay, flagged False
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    application: Mapped[Application] = relationship(back_populates="claims")


class GraphNode(Base):
    """Materialised snapshot of engine output; the engine/DAG rules remain authoritative."""
    __tablename__ = "graph_nodes"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    value: Mapped[Optional[str]] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(Text, default="")
    supporting_claim_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_recalculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        ForeignKeyConstraint(["application_id", "source_id"], ["graph_nodes.application_id", "graph_nodes.node_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["application_id", "target_id"], ["graph_nodes.application_id", "graph_nodes.node_id"], ondelete="CASCADE"),
        Index("ix_edges_target", "application_id", "target_id"),
    )
    application_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="depends_on")
    reason: Mapped[str] = mapped_column(Text)


class ReconciliationCheck(Base):
    __tablename__ = "reconciliation_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(60))
    rule_type: Mapped[str] = mapped_column(String(40))            # revenue_reconciliation | cross_document
    compared_claim_ids: Mapped[list] = mapped_column(JSON, default=list)
    reported_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    recognized_adjustments: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    residual: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 6))
    status: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text, default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only. UPDATE/DELETE raise (see listeners)."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_app_ts", "application_id", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)  # no cascade: history survives
    event_type: Mapped[str] = mapped_column(String(40))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(100), default="system")
    target_entity: Mapped[str] = mapped_column(String(80))
    previous_state: Mapped[Optional[Any]] = mapped_column(JSON)
    new_state: Mapped[Optional[Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text, default="")
    affected_node_ids: Mapped[list] = mapped_column(JSON, default=list)
    document_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    recommendation_before: Mapped[Optional[str]] = mapped_column(String(40))
    recommendation_after: Mapped[Optional[str]] = mapped_column(String(40))


@event.listens_for(AuditEvent, "before_update")
def _no_update(*_): raise RuntimeError("audit_events are append-only")


@event.listens_for(AuditEvent, "before_delete")
def _no_delete(*_): raise RuntimeError("audit_events are append-only")


class SimulationRun(Base):
    """Counterfactuals are stored separately and never touch live state."""
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    excluded_node_id: Mapped[str] = mapped_column(String(60))
    actor: Mapped[str] = mapped_column(String(100), default="analyst")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    original: Mapped[Any] = mapped_column(JSON)
    simulated: Mapped[Any] = mapped_column(JSON)
    changes: Mapped[Any] = mapped_column(JSON)
