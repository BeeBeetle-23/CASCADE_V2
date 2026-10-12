"""python -m app.db.init_db [--reset]   Safe to run repeatedly."""
import argparse
import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.engine import BASIS, Engine
from . import models as m
from .base import Base
from .session import SessionLocal, engine

DEMO_APP_ID = "app_alpha_tech"
DOC_FIXTURES = {  # graph doc node -> (doc type, filename)
    "doc_bank": ("bank_statement", "alpha_bank_statement_FY2025-26.pdf"),
    "doc_tax": ("income_tax_return", "alpha_itr_FY2025-26.pdf"),
    "doc_pnl": ("profit_and_loss", "alpha_pnl_FY2025-26.pdf"),
}
CLAIM_TYPES = {
    "c_bank_inflow": "bank_inflow_total", "a_internal": "internal_transfer", "a_loan": "loan_proceeds",
    "a_refund": "refund_or_other_credit", "a_equity": "owner_equity_contribution",
    "c_tax_rev": "gross_revenue_tax", "c_pnl_rev": "gross_revenue_pnl",
    "c_cfads": "cash_available_for_debt_service", "c_ds": "scheduled_debt_service",
    "c_ca": "current_assets", "c_cl": "current_liabilities",
}


def create_schema() -> None:
    Base.metadata.create_all(engine)


def seed_scenario(db: Session, app: m.Application, key: str, reset_documents: bool = False) -> None:
    """(Re)populate documents/claims for a scenario from the shared engine, then derive nodes/edges/checks through the
    same DB->engine path used everywhere else. Audit history is always kept."""
    from app.services.state_store import load_engine, persist_snapshot   # lazy: avoids an import cycle
    eng = Engine(key)
    for c in db.scalars(select(m.Claim).where(m.Claim.application_id == app.id)): c.supersedes_claim_id = None
    db.flush()
    for model in (m.GraphEdge, m.GraphNode, m.ReconciliationCheck, m.Claim):
        for row in db.scalars(select(model).where(model.application_id == app.id)):
            db.delete(row)
    db.flush()
    if reset_documents:
        for d in db.scalars(select(m.Document).where(m.Document.application_id == app.id)): db.delete(d)
        db.flush()
    docs = {d.node_id: d for d in db.scalars(select(m.Document).where(m.Document.application_id == app.id))}
    for node_id, (dtype, fname) in DOC_FIXTURES.items():
        if node_id not in docs:
            d = m.Document(application_id=app.id, node_id=node_id, doc_type=dtype, type_confirmed=True)
            d.versions.append(m.DocumentVersion(
                version_number=1, original_filename=fname, storage_path=None, processing_status="ready",
                file_hash=hashlib.sha256(f"demo-fixture:{fname}".encode()).hexdigest(),
                verification_status="verified", reporting_period=BASIS.period, extraction_mode="demo_fixture",
                diagnostics=[{"level": "info", "code": "demo_fixture",
                              "message": "Synthetic preloaded demonstration data, not extracted from a PDF."}]))
            db.add(d); docs[node_id] = d
        else:
            for v in docs[node_id].versions: v.verification_status = "verified"
    db.flush()
    for nid in eng.g.nodes:
        if nid not in CLAIM_TYPES: continue
        doc = docs[next(iter(eng.g.predecessors(nid)))]
        db.add(m.Claim(application_id=app.id, entity_id=app.entity_id, node_id=nid, claim_type=CLAIM_TYPES[nid],
                       value=eng.values[nid], currency=BASIS.currency, unit=BASIS.unit,
                       source_document_id=doc.id, document_version_id=doc.versions[-1].id,
                       page_number=None, source_excerpt=None, bbox=None, confidence=None,  # no fabricated provenance
                       extraction_mode="demo_fixture", verification_status="verified"))
    db.flush()
    app.scenario_key = key
    persist_snapshot(db, app, load_engine(db, app))
    rec = eng.state["recommendation"]
    db.add(m.AuditEvent(application_id=app.id, event_type="scenario_loaded", actor="system", target_entity=key,
                        new_state={"scenario": eng.sc["name"]}, reason=f"Loaded scenario {eng.sc['name']}",
                        affected_node_ids=list(eng.g.nodes), recommendation_after=rec["value"]))


def seed_demo(db: Session) -> m.Application:
    app = db.get(m.Application, DEMO_APP_ID)
    if app is None:
        app = m.Application(id=DEMO_APP_ID, company_name="Alpha Tech LLC", entity_id=BASIS.entity,
                            requested_amount=250, currency="INR", reporting_period=BASIS.period)
        db.add(app); db.flush()
        seed_scenario(db, app, "A")
    db.commit()
    return app


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--reset", action="store_true", help="drop all tables first")
    if p.parse_args().reset: Base.metadata.drop_all(engine)
    create_schema()
    with SessionLocal() as db: seed_demo(db)
    print("Database ready; demo application:", DEMO_APP_ID)


if __name__ == "__main__": main()
