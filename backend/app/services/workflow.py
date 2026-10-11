"""Orchestration: mutate DB -> rebuild engine -> cascade summary -> snapshot -> audit -> commit."""
from typing import Callable, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.errors import DomainError
from app.db import models as m
from .engine import Engine
from .graph_view import to_reactflow
from .state_store import (DOC_NODE, current_claims, current_version, doc_node, load_engine, persist_snapshot,
                          record_audit, support_map)


def graph_payload(db, app, eng=None, **kw) -> dict:
    eng = eng or load_engine(db, app)
    stamps = {n.node_id: n.last_recalculated_at.isoformat() for n in
              db.scalars(select(m.GraphNode).where(m.GraphNode.application_id == app.id))
              if n.last_recalculated_at}
    return to_reactflow(eng, app.id, support=support_map(db, app.id, eng), recalculated=stamps, **kw)

def _r(x): return x() if callable(x) else x


def apply_change(db: Session, app: m.Application, *, initiator, event_type: str, actor: str, reason,
                 prev, new, mutate: Callable[[], None], version_ids=()) -> dict:
    """initiator/reason/new/version_ids may be callables, resolved after `mutate` (needed for uploads)."""
    before = load_engine(db, app)
    mutate()
    initiator, reason, new, version_ids = _r(initiator), _r(reason), _r(new), _r(version_ids)
    after = load_engine(db, app)
    summary = after.cascade_summary(initiator, before.state)
    persist_snapshot(db, app, after)
    record_audit(db, app.id, event_type, actor, initiator, prev, new, reason, list(summary["changed"]), list(version_ids),
                 before.state["recommendation"]["value"], after.state["recommendation"]["value"])
    db.commit()
    return dict(**summary, graph=graph_payload(db, app, after, affected=set(summary["changed"]), initiator=initiator))


def get_claim(db: Session, claim_id: str) -> m.Claim:
    c = db.get(m.Claim, claim_id)
    if c is None: raise DomainError(404, f"Claim {claim_id} not found")
    return c


def get_document(db: Session, doc_id: str) -> m.Document:
    d = db.get(m.Document, doc_id)
    if d is None: raise DomainError(404, f"Document {doc_id} not found")
    return d


def set_claim_verification(db, app, claim_id: str, status: str, actor: str, reason: str) -> dict:
    c = get_claim(db, claim_id)
    if c.application_id != app.id: raise DomainError(404, "Claim does not belong to this application")
    if not c.is_current: raise DomainError(409, "Only current claims can be verified; this claim was superseded")
    prev = {"claim_id": c.id, "verification_status": c.verification_status}
    def mutate(): c.verification_status = status
    return apply_change(db, app, initiator=c.node_id, event_type="verification_changed", actor=actor,
                        reason=reason or f"Claim {c.id} marked {status}", prev=prev,
                        new={"claim_id": c.id, "verification_status": status}, mutate=mutate,
                        version_ids=[c.document_version_id])


def correct_claim(db, app, claim_id: str, new_value, actor: str, reason: str) -> dict:
    old = get_claim(db, claim_id)
    if old.application_id != app.id: raise DomainError(404, "Claim does not belong to this application")
    if not old.is_current: raise DomainError(409, "Only current claims can be corrected")
    holder = {}
    def mutate():
        old.is_current = False   # preserved with its value; superseded by the correction
        new = m.Claim(application_id=old.application_id, entity_id=old.entity_id, node_id=old.node_id,
                      claim_type=old.claim_type, value=new_value, currency=old.currency, unit=old.unit,
                      period_start=old.period_start, period_end=old.period_end, source_document_id=old.source_document_id,
                      document_version_id=old.document_version_id, page_number=old.page_number,
                      source_excerpt=old.source_excerpt, bbox=old.bbox, confidence=None, extraction_mode="manual_correction",
                      verification_status="verified", supersedes_claim_id=old.id)
        db.add(new); db.flush(); holder["new"] = new
    r = apply_change(db, app, initiator=old.node_id, event_type="claim_corrected", actor=actor, reason=reason,
                     prev={"claim_id": old.id, "value": str(old.value)}, new={"value": str(new_value)},
                     mutate=mutate, version_ids=[old.document_version_id])
    return r


def set_document_verification(db, doc_id: str, status: str, actor: str, reason: str) -> dict:
    doc = get_document(db, doc_id); app = db.get(m.Application, doc.application_id)
    node, v = doc_node(doc), current_version(db, doc.id)
    if not node: raise DomainError(409, "Confirm the document type first; it is not yet part of the dependency graph")
    prev = {"version_id": v.id, "verification_status": v.verification_status}
    def mutate(): v.verification_status = status
    return apply_change(db, app, initiator=node, event_type="verification_changed", actor=actor,
                        reason=reason or f"Document {doc.id} v{v.version_number} marked {status}", prev=prev,
                        new={"version_id": v.id, "verification_status": status}, mutate=mutate, version_ids=[v.id])


def accept_review(db, doc_id: str, actor: str) -> dict:
    """Human has reviewed the extraction: verify the current version and its pending claims."""
    doc = get_document(db, doc_id); app = db.get(m.Application, doc.application_id)
    node, v = doc_node(doc), current_version(db, doc.id)
    if not node: raise DomainError(409, "Confirm the document type first")
    def mutate():
        v.verification_status = "verified"; v.processing_status = "ready"
        for c in current_claims(db, app.id):
            if c.document_version_id == v.id and c.verification_status == "pending_review": c.verification_status = "verified"
    return apply_change(db, app, initiator=node, event_type="document_review_accepted", actor=actor,
                        reason=f"Extraction of {doc.id} v{v.version_number} reviewed and accepted", prev=None,
                        new={"version_id": v.id}, mutate=mutate, version_ids=[v.id])


def recalculate(db, app, actor: str = "system") -> dict:
    eng = load_engine(db, app)
    persist_snapshot(db, app, eng)
    rec = eng.state["recommendation"]["value"]
    record_audit(db, app.id, "recalculated", actor, "application", None, {"recommendation": rec},
                 "Full recalculation from current evidence", [], [], rec, rec)
    db.commit()
    return dict(initiator="application", downstream_order=[], changed={}, unchanged_downstream=[],
                independent_unchanged=list(eng.g.nodes), recommendation=eng.state["recommendation"],
                graph=graph_payload(db, app, eng))


def simulate(db, app, excluded_node_id: str, actor: str) -> dict:
    eng = load_engine(db, app)
    if excluded_node_id not in eng.g: raise DomainError(404, f"Unknown graph node {excluded_node_id}")
    if eng.g.nodes[excluded_node_id]["type"] not in ("document", "claim", "adjustment"):
        raise DomainError(422, "Only evidence nodes (documents, claims, adjustments) can be excluded in a simulation")
    sim = eng.simulate_without(excluded_node_id)
    changed = sim["original"] != sim["simulated"]
    run = m.SimulationRun(application_id=app.id, excluded_node_id=excluded_node_id, actor=actor,
                          original=sim["original"], simulated=sim["simulated"], changes=sim["changes"])
    db.add(run); db.commit()     # live graph, claims and audit trail are untouched
    return dict(id=run.id, excluded_node_id=excluded_node_id, original_recommendation=sim["original"],
                simulated_recommendation=sim["simulated"], recommendation_changed=changed, changes=sim["changes"],
                created_at=run.created_at,
                simulated_graph=graph_payload(db, app, eng, affected=set(sim["changes"]), initiator=excluded_node_id,
                                              state=sim["state"]))
