# CASCADE — Underwriting Document Cascade Engine (backend)

The LLM perceives and narrates; deterministic code validates, calculates, and decides state.
Decision support only — never a credit decision, and discrepancies are never findings of fraud.

## Layout
`backend/app/services/` — `rules.py` (financial rules), `engine.py` (NetworkX DAG, cascade, simulation),
`state_store.py` (DB↔engine), `workflow.py` (verify/correct/simulate with audit), `pdf_extraction.py`,
`claim_mapping.py` (LLM + deterministic mapping, validation), `ingestion.py` (upload/versions/diff), `report.py`.
`backend/app/api/` routes · `db/` models, session, seeding · `schemas/` Pydantic models.

## Run locally (Windows PowerShell)
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.init_db          # creates tables + seeds Alpha Tech LLC (safe to repeat; add --reset to wipe)
uvicorn app.main:app --reload --port 8000
```
API: http://localhost:8000 · Swagger UI: http://localhost:8000/docs · Health: http://localhost:8000/health
The server also creates tables and seeds the demo on startup, so `init_db` is optional.
There is no Alembic migration step yet: schema is created with `create_all`. For schema changes use `init_db --reset` (SQLite dev).

## Docker (FastAPI + SQLite)
```powershell
docker compose up --build        # API on :8000, SQLite file on the cascade_data volume
```
PostgreSQL (optional): `docker compose --profile postgres up -d db`, then
`$env:DATABASE_URL="postgresql+psycopg://cascade:cascade@localhost:5432/cascade"` before starting the API locally.

## LLM mapping (optional)
Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) in the backend environment. Without a key the deterministic
parser is used and the UI/API report `deterministic_fallback`; `llm_mapped` appears only when the model was really called.
Every extracted claim is validated in code (schema, excerpt present on the cited page, value present in excerpt, allowed
type for the document) and starts as `pending_review`.

## Demo flow
`POST /demo/load {"scenario":"A"|"B"|"C"}` → `POST /documents/{id}/verify {"status":"unverified"}` (cascade result with
changed/unchanged nodes) → `GET /applications/app_alpha_tech/audit` → verify again to recompute → `POST /demo/reset`.
Counterfactual: `POST /applications/app_alpha_tech/simulate {"excluded_node_id":"doc_bank"}` (live state untouched).
Real PDFs: upload `backend/sample_docs/*.pdf` to a new application (`POST /applications/{id}/documents`), then
`POST /documents/{id}/review/accept` after reviewing claims.

## Tests
```powershell
cd backend
python -m pytest tests -q
```
`test_core.py`, `test_pure.py`, `test_graph_view.py` need only networkx/pdfplumber. `test_db_schemas.py` and `test_api.py`
need the full requirements. Tests use fixed synthetic data and a mocked LLM client; no network is needed.

## Troubleshooting
- **Port in use:** `uvicorn app.main:app --port 8001`.
- **CORS errors:** the API allows http://localhost:5173 (Vite default); edit `allow_origins` in `app/main.py` otherwise.
- **`python-multipart` error on upload:** `pip install python-multipart`.
- **Scanned PDF, no claims:** reported as `needs_ocr`; OCR is not implemented.
- **LLM errors:** codes `llm_rate_limited`, `llm_timeout`, `llm_auth`, `llm_unreachable`, `llm_bad_response` appear in the
  document diagnostics and the deterministic parser is used instead.
- **Stale schema after code changes:** `python -m app.db.init_db --reset`.
