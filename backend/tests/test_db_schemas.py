"""Needs pydantic + sqlalchemy (your environment). Run: python -m pytest tests -q"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import pytest
from decimal import Decimal
from pydantic import ValidationError
from sqlalchemy import select
from app.db import models as m
from app.db.base import Base
from app.db.init_db import DEMO_APP_ID, seed_demo, seed_scenario
from app.db.session import make_engine
from sqlalchemy.orm import sessionmaker
from app.schemas import (ApplicationCreate, BoundingBox, ClaimCorrectionRequest, ExtractedClaimCandidate,
                         GraphPayload, ClaimOut, AuditEventOut)
from app.services.engine import Engine
from app.services.graph_view import to_reactflow


@pytest.fixture()
def db():
    eng = make_engine("sqlite://"); Base.metadata.create_all(eng)
    with sessionmaker(bind=eng, expire_on_commit=False)() as s: yield s


def test_seed_is_idempotent(db):
    seed_demo(db); seed_demo(db)
    assert len(db.scalars(select(m.Application)).all()) == 1
    assert len(db.scalars(select(m.Document)).all()) == 3
    assert len(db.scalars(select(m.Claim)).all()) == 10
    assert len(db.scalars(select(m.AuditEvent)).all()) == 1


def test_scenario_switch_keeps_audit_and_docs(db):
    app = seed_demo(db); seed_scenario(db, app, "C"); db.commit()
    c = db.scalars(select(m.GraphNode).where(m.GraphNode.node_id == "chk_recon")).one()
    assert (c.status, c.value) == ("red", "3")
    assert len(db.scalars(select(m.AuditEvent)).all()) == 2
    assert len(db.scalars(select(m.Document)).all()) == 3
    assert len(db.scalars(select(m.Claim)).all()) == 9    # C has no refund adjustment


def test_demo_claims_have_no_fabricated_provenance(db):
    seed_demo(db)
    for c in db.scalars(select(m.Claim)):
        assert c.page_number is None and c.source_excerpt is None and c.bbox is None
        assert c.extraction_mode == "demo_fixture"
        ClaimOut.model_validate(c)


def test_audit_is_append_only(db):
    seed_demo(db)
    ev = db.scalars(select(m.AuditEvent)).first()
    ev.reason = "tampered"
    with pytest.raises(RuntimeError): db.commit()
    db.rollback()
    db.delete(db.scalars(select(m.AuditEvent)).first())
    with pytest.raises(RuntimeError): db.commit()
    db.rollback()


def test_audit_schema_roundtrip(db):
    seed_demo(db); AuditEventOut.model_validate(db.scalars(select(m.AuditEvent)).first())


def test_graph_payload_validates():
    GraphPayload.model_validate(to_reactflow(Engine("B"), DEMO_APP_ID))


def test_request_validation():
    assert ApplicationCreate(company_name=" Acme ", requested_amount="10", currency="inr", reporting_period="FY26").currency == "INR"
    for bad in [dict(company_name="", requested_amount=1), dict(company_name="x", requested_amount=0),
                dict(company_name="x", requested_amount=1, currency="RUPEE")]:
        with pytest.raises(ValidationError): ApplicationCreate(reporting_period="FY26", **bad)
    with pytest.raises(ValidationError): ClaimCorrectionRequest(new_value=1, reason="x")
    with pytest.raises(ValidationError): BoundingBox(x0=5, y0=0, x1=1, y1=1)


def test_extracted_candidate_rules():
    ok = dict(claim_type="gross_revenue_tax", value="80", currency="inr", unit="lakh", page_number=2,
              source_excerpt="Gross receipts 80", confidence=0.9)
    assert ExtractedClaimCandidate(**ok).currency == "INR"
    for patch in [dict(claim_type="made_up"), dict(page_number=0), dict(confidence=1.5), dict(source_excerpt="")]:
        with pytest.raises(ValidationError): ExtractedClaimCandidate(**{**ok, **patch})
