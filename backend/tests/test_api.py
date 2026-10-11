"""API integration tests. Need: fastapi, httpx, sqlalchemy, pydantic, pytest. No network or LLM is used."""
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from pdfgen import BANK, PNL, TAX, make_pdf

APP = "app_alpha_tech"


@pytest.fixture()
def client():
    from app.db.base import Base
    from app.db.session import engine
    Base.metadata.drop_all(engine)
    from app.main import app
    with TestClient(app) as c: yield c


def graph(c, app=APP): return {n["id"]: n["data"] for n in c.get(f"/applications/{app}/graph").json()["nodes"]}
def claim_id(c, node, app=APP): return next(x["id"] for x in c.get(f"/applications/{app}/claims").json() if x["node_id"] == node)
def doc_id(c, doc_type, app=APP): return next(d["id"] for d in c.get(f"/applications/{app}/documents").json() if d["doc_type"] == doc_type)
def pdf(lines): return {"file": ("x.pdf", make_pdf([lines]), "application/pdf")}


def test_health_and_dashboard(client):
    assert client.get("/health").json()["status"] == "ok"
    apps = client.get("/applications").json()
    assert apps[0]["company_name"] == "Alpha Tech LLC" and apps[0]["document_count"] == 3
    assert apps[0]["recommendation"] == "APPROVE_CANDIDATE_PENDING_REVIEW"


def test_graph_from_backend(client):
    g = client.get(f"/applications/{APP}/graph").json()
    assert len(g["nodes"]) == 19 and len(g["edges"]) > 20
    assert graph(client)["chk_recon"]["status"] == "green"


def test_cascade_via_api_and_restore(client):
    bank_doc = doc_id(client, "bank_statement")
    r = client.post(f"/documents/{bank_doc}/verify", json={"status": "unverified", "reason": "test"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendation"]["status"] == "needs_review"
    assert "m_dscr" not in body["changed"] and "chk_contra" not in body["changed"]
    g = graph(client)
    assert g["chk_recon"]["status"] == "unavailable" and g["m_dscr"]["value"] == "1.50"
    ev = client.get(f"/applications/{APP}/audit").json()
    assert ev[-1]["event_type"] == "verification_changed" and "chk_recon" in ev[-1]["affected_node_ids"]
    client.post(f"/documents/{bank_doc}/verify", json={"status": "verified"})
    assert graph(client)["recommendation"]["status"] == "current"
    assert len(client.get(f"/applications/{APP}/audit").json()) == 3          # history retained


def test_claim_correction_preserves_history(client):
    switch = client.post("/demo/load", json={"scenario": "B"}); assert switch.status_code == 200
    assert graph(client)["chk_contra"]["status"] == "red"
    cid = claim_id(client, "c_pnl_rev")
    r = client.post(f"/claims/{cid}/correct", json={"new_value": "80", "reason": "P&L typo corrected"})
    assert r.status_code == 200 and graph(client)["chk_contra"]["status"] == "green"
    h = client.get(f"/claims/{claim_id(client, 'c_pnl_rev')}/history").json()
    assert len(h["values"]) == 2 and h["values"][-1]["supersedes_claim_id"] == cid
    assert h["events"][-1]["previous_state"]["value"].startswith("60")
    assert client.post(f"/claims/{cid}/correct", json={"new_value": "1", "reason": "again"}).status_code == 409  # superseded


def test_simulation_leaves_live_state(client):
    before, n_audit = graph(client), len(client.get(f"/applications/{APP}/audit").json())
    r = client.post(f"/applications/{APP}/simulate", json={"excluded_node_id": "doc_bank"})
    assert r.status_code == 200 and r.json()["recommendation_changed"] is True
    assert graph(client) == before and len(client.get(f"/applications/{APP}/audit").json()) == n_audit
    assert client.post(f"/applications/{APP}/simulate", json={"excluded_node_id": "chk_recon"}).status_code == 422
    assert client.get(f"/applications/{APP}/simulations").json()[0]["excluded_node_id"] == "doc_bank"


def test_scenarios_and_reset(client):
    for key, node, status in [("C", "chk_recon", "red"), ("B", "chk_contra", "red"), ("A", "chk_recon", "green")]:
        client.post("/demo/load", json={"scenario": key}); assert graph(client)[node]["status"] == status
    client.post("/applications/%s/simulate" % APP, json={"excluded_node_id": "doc_bank"})
    client.post(f"/documents/{doc_id(client, 'bank_statement')}/verify", json={"status": "unverified"})
    assert client.post("/demo/reset").status_code == 200
    assert graph(client)["recommendation"]["status"] == "current"


def test_upload_pdf_extract_review_and_report(client):
    app = client.post("/applications", json={"company_name": "Alpha Tech LLC", "requested_amount": "250", "reporting_period": "FY2025-26"}).json()["id"]
    for lines in (BANK, TAX, PNL):
        r = client.post(f"/applications/{app}/documents", files=pdf(lines)); assert r.status_code == 201, r.text
        assert r.json()["extraction_mode"] == "deterministic_fallback" and r.json()["claims_created"] >= 1
    claims = client.get(f"/applications/{app}/claims").json()
    bank = next(c for c in claims if c["node_id"] == "c_bank_inflow")
    assert float(bank["value"]) == 100 and bank["page_number"] == 1 and "Total credits" in bank["source_excerpt"]
    assert bank["bbox"] is not None and bank["verification_status"] == "pending_review"
    assert graph(client, app)["recommendation"]["status"] == "needs_review"      # nothing verified yet
    for d in client.get(f"/applications/{app}/documents").json():
        assert client.post(f"/documents/{d['id']}/review/accept").status_code == 200
    g = graph(client, app)
    assert g["chk_recon"]["status"] == "green" and g["recommendation"]["value"] == "APPROVE_CANDIDATE_PENDING_REVIEW"
    rep = client.get(f"/applications/{app}/report").json()
    assert rep["recommendation"]["current"] is True and rep["consistency_and_reconciliation"][0]["evidence"][0]["page"] == 1
    assert "Underwriting report" in client.get(f"/applications/{app}/report.html").text
    assert client.get(f"/applications/{app}/report.csv").text.startswith("section,")


def test_upload_validation(client):
    app = APP
    assert client.post(f"/applications/{app}/documents", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post(f"/applications/{app}/documents", files={"file": ("a.pdf", b"not a pdf", "application/pdf")}).status_code == 415
    assert client.post(f"/applications/{app}/documents", files={"file": ("a.pdf", b"", "application/pdf")}).status_code == 422
    scanned = client.post(f"/applications/{app}/documents", files=pdf([""]))
    assert scanned.status_code == 201 and scanned.json()["claims_created"] == 0
    assert any(w["code"] == "needs_ocr" for w in scanned.json()["warnings"])
    assert client.get("/applications/nope").status_code == 404


def test_new_version_diff_and_recalculation(client):
    app = client.post("/applications", json={"company_name": "Alpha Tech LLC", "requested_amount": "250", "reporting_period": "FY2025-26"}).json()["id"]
    docs = {}
    for lines in (BANK, TAX, PNL):
        r = client.post(f"/applications/{app}/documents", files=pdf(lines)).json(); docs[r["document"]["doc_type"]] = r["document"]["id"]
        client.post(f"/documents/{r['document']['id']}/review/accept")
    assert graph(client, app)["chk_contra"]["status"] == "green"
    new_pnl = [l.replace("Gross revenue 80", "Gross revenue 60") for l in PNL]
    r = client.post(f"/documents/{docs['profit_and_loss']}/versions", files=pdf(new_pnl)); assert r.status_code == 201, r.text
    diff = r.json()["diff"]; item = next(i for i in diff["items"] if i["claim_type"] == "gross_revenue_pnl")
    assert (item["old_value"], item["new_value"]) == ("80", "60") and "chk_contra" in diff["affected_node_ids"]
    assert len(r.json()["document"]["versions"]) == 2
    assert graph(client, app)["chk_contra"]["status"] == "unavailable"           # new version not yet reviewed
    client.post(f"/documents/{docs['profit_and_loss']}/review/accept")
    assert graph(client, app)["chk_contra"]["status"] == "red"
    assert client.post(f"/documents/{docs['profit_and_loss']}/versions", files=pdf(new_pnl)).status_code == 409   # identical
    old_ver = client.get(f"/applications/{app}/claims", params={"include_history": True}).json()
    assert sum(1 for c in old_ver if c["claim_type"] == "gross_revenue_pnl") == 2   # old claim preserved


def test_llm_mapping_is_validated_and_mocked():
    from app.services.claim_mapping import map_claims
    pages = [{"page": 1, "text": "Gross receipts 80 lakh\nTotal income 12", "blocks": [], "tables": []}]
    good = [dict(claim_type="gross_revenue_tax", value="80", currency="INR", unit="lakh", page_number=1, source_excerpt="Gross receipts 80 lakh", confidence=0.9),
            dict(claim_type="gross_revenue_tax", value="999", currency="INR", unit="lakh", page_number=1, source_excerpt="invented line 999", confidence=0.9),
            dict(claim_type="current_assets", value="5", currency="INR", unit="lakh", page_number=1, source_excerpt="Gross receipts 80 lakh", confidence=0.9)]
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: SimpleNamespace(content=[SimpleNamespace(text="```json\n" + json.dumps(good) + "\n```")])))
    r = map_claims(pages, "income_tax_return", use_llm=True, api_key=None, model="m", client=client)
    assert r.mode == "llm_mapped" and len(r.accepted) == 1 and str(r.accepted[0].value_lakh) == "80"
    assert sum(d["code"] == "claim_rejected" for d in r.diagnostics) == 2          # fabricated + wrong-type rejected
    def boom(**k):
        class RateLimitError(Exception): pass
        raise RateLimitError()
    r = map_claims(pages, "income_tax_return", use_llm=True, api_key=None, model="m", client=SimpleNamespace(messages=SimpleNamespace(create=boom)))
    assert r.mode == "deterministic_fallback" and any(d["code"] == "llm_rate_limited" for d in r.diagnostics)
