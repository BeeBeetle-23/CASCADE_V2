"""DB <-> Engine bridge: rebuild the engine from rows, persist snapshots/checks, append audit events."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import models as m
from app.db.init_db import CLAIM_TYPES
from . import rules
from .engine import ALL_CLAIM_NODES, Engine

DOC_NODE = {"bank_statement": "doc_bank", "income_tax_return": "doc_tax", "profit_and_loss": "doc_pnl"}
NODE_FOR_CLAIM_TYPE = {v: k for k, v in CLAIM_TYPES.items()}


def doc_node(doc: m.Document) -> Optional[str]:
    return doc.node_id or DOC_NODE.get(doc.doc_type)


def current_version(db: Session, doc_id: str) -> Optional[m.DocumentVersion]:
    db.flush()
    vs = db.scalars(select(m.DocumentVersion).where(m.DocumentVersion.document_id == doc_id)
                    .order_by(m.DocumentVersion.version_number)).all()
    cur = [v for v in vs if v.is_current]
    return cur[-1] if cur else (vs[-1] if vs else None)


def current_claims(db: Session, app_id: str) -> list[m.Claim]:
    db.flush()
    return list(db.scalars(select(m.Claim).where(m.Claim.application_id == app_id, m.Claim.is_current.is_(True))
                           .order_by(m.Claim.created_at, m.Claim.id)))


def load_engine(db: Session, app: m.Application) -> Engine:
    db.flush()
    docs = db.scalars(select(m.Document).where(m.Document.application_id == app.id)).all()
    verification, values, bases = {}, {}, {}
    for d in docs:
        node, v = doc_node(d), current_version(db, d.id)
        if node and v:
            verification[node] = "verified" if v.verification_status == "verified" else "unverified"
    for c in current_claims(db, app.id):
        if c.node_id not in ALL_CLAIM_NODES or c.value is None: continue
        values[c.node_id] = Decimal(c.value)
        verification[c.node_id] = "verified" if c.verification_status == "verified" else "unverified"
        period = f"{c.period_start}/{c.period_end}" if c.period_start and c.period_end else app.reporting_period
        bases[c.node_id] = rules.Basis(c.entity_id, period, c.currency, c.unit)
    return Engine(app.scenario_key, values=values, verification=verification, bases=bases)


def support_map(db: Session, app_id: str, eng: Engine) -> dict[str, list[str]]:
    own: dict[str, list[str]] = {}
    for c in current_claims(db, app_id): own.setdefault(c.node_id, []).append(c.id)
    out: dict[str, list[str]] = {}
    for n in nx.topological_sort(eng.g):
        if n in ALL_CLAIM_NODES: out[n] = own.get(n, [])
        else: out[n] = sorted({i for p in eng.g.predecessors(n) for i in out.get(p, [])})
    return out


def persist_snapshot(db: Session, app: m.Application, eng: Engine) -> None:
    """Upsert the materialised graph + check rows (ORM-level, so the session identity map stays consistent)."""
    support = support_map(db, app.id, eng)
    ts = datetime.now(timezone.utc)
    db.flush()
    nodes = {n.node_id: n for n in db.scalars(select(m.GraphNode).where(m.GraphNode.application_id == app.id))}
    edges = {(e.source_id, e.target_id): e for e in db.scalars(select(m.GraphEdge).where(m.GraphEdge.application_id == app.id))}
    checks = {c.node_id: c for c in db.scalars(select(m.ReconciliationCheck).where(m.ReconciliationCheck.application_id == app.id))}
    edges_now = {(a, b): d["reason"] for a, b, d in eng.g.edges(data=True)}
    for key, e in edges.items():
        if key not in edges_now: db.delete(e)
    db.flush()
    for nid, row in nodes.items():
        if nid not in eng.g: db.delete(row)
    db.flush()
    for nid, data in eng.g.nodes(data=True):
        s_ = eng.state[nid]
        row = nodes.get(nid) or m.GraphNode(application_id=app.id, node_id=nid)
        row.node_type, row.label, row.status, row.value, row.reason = data["type"], data["label"], s_["status"], s_["value"], s_["reason"]
        row.supporting_claim_ids, row.last_recalculated_at = support[nid], ts
        if nid not in nodes: db.add(row)
    db.flush()
    for (a, b), why in edges_now.items():
        row = edges.get((a, b)) or m.GraphEdge(application_id=app.id, source_id=a, target_id=b)
        row.reason = why
        if (a, b) not in edges: db.add(row)
    dec = lambda x: Decimal(x) if x is not None else None
    for node, d in eng.check_details().items():
        row = checks.get(node) or m.ReconciliationCheck(application_id=app.id, node_id=node)
        row.rule_type = d["rule_type"]
        row.compared_claim_ids = sorted({i for c in d["compared"] for i in support.get(c, [])})
        row.reported_difference, row.recognized_adjustments = dec(d["reported_difference"]), dec(d["adjustments_total"])
        row.residual, row.threshold = dec(d["residual"]), dec(d["threshold"])
        row.status, row.explanation, row.computed_at = d["status"], d["explanation"], ts
        if node not in checks: db.add(row)
    app.status = eng.state["recommendation"]["status"]
    app.updated_at = ts
    db.flush()


def record_audit(db: Session, app_id: str, event_type: str, actor: str, target: str, prev, new, reason: str,
                 affected: list[str], version_ids: list[str], rec_before: Optional[str], rec_after: Optional[str]) -> m.AuditEvent:
    ev = m.AuditEvent(application_id=app_id, event_type=event_type, actor=actor, target_entity=target, previous_state=prev,
                      new_state=new, reason=reason, affected_node_ids=affected, document_version_ids=version_ids,
                      recommendation_before=rec_before, recommendation_after=rec_after)
    db.add(ev); db.flush()
    return ev
