"""Upload validation, storage, versioning, processing (extract -> classify -> map -> validate) and version diffs."""
import hashlib
import logging
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional
import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.errors import DomainError
from app.db import models as m
from . import integrity, text_utils as tu
from .claim_mapping import map_claims
from .integrity import finding
from .pdf_extraction import extract_pdf
from .state_store import DOC_NODE, NODE_FOR_CLAIM_TYPE, current_claims, current_version, doc_node, load_engine
from .workflow import apply_change

log = logging.getLogger("cascade.ingest")


def safe_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return (s or "upload.pdf")[:120]


def validate_upload(filename: str, data: bytes) -> None:
    if not (filename or "").lower().endswith(".pdf"): raise DomainError(415, "Only .pdf files are accepted")
    if not data: raise DomainError(422, "The uploaded file is empty")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DomainError(413, f"File exceeds the {settings.max_upload_mb} MB limit")
    if not data.startswith(b"%PDF-"): raise DomainError(415, "File content is not a PDF (missing %PDF header)")


def _store(app_id: str, data: bytes, sha: str, safe: str) -> str:
    d = Path(settings.upload_dir) / app_id; d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sha[:16]}_{safe}"
    if not p.exists(): p.write_bytes(data)
    return str(p)


def _new_version(db, doc, filename, data, app_id, number) -> m.DocumentVersion:
    sha = hashlib.sha256(data).hexdigest()
    diags = []
    dup = db.scalars(select(m.DocumentVersion).join(m.Document).where(
        m.Document.application_id == app_id, m.DocumentVersion.file_hash == sha, m.DocumentVersion.document_id != doc.id)).first()
    if dup: diags.append(finding("warning", "duplicate_file", f"Identical file (SHA-256) already uploaded as {dup.original_filename}.", file_hash=sha))
    v = m.DocumentVersion(document_id=doc.id, version_number=number, original_filename=safe_filename(filename), file_hash=sha,
                          storage_path=_store(app_id, data, sha, safe_filename(filename)), processing_status="uploaded",
                          verification_status="pending_review", is_current=True, diagnostics=diags)
    db.add(v); db.flush()
    return v


def create_document(db, app, filename, data) -> tuple[m.Document, m.DocumentVersion]:
    doc = m.Document(application_id=app.id, doc_type="unknown", type_confirmed=False)
    db.add(doc); db.flush()
    return doc, _new_version(db, doc, filename, data, app.id, 1)


def add_version(db, doc, filename, data) -> m.DocumentVersion:
    vs = list(db.scalars(select(m.DocumentVersion).where(m.DocumentVersion.document_id == doc.id)))
    cur = current_version(db, doc.id)
    if cur and cur.file_hash == hashlib.sha256(data).hexdigest():
        raise DomainError(409, "The uploaded file is identical to the current version")
    for v in vs: v.is_current = False
    return _new_version(db, doc, filename, data, doc.application_id, max((v.version_number for v in vs), default=0) + 1)


def assign_type(db, doc, dtype: str, *, confirmed: bool, strict: bool) -> bool:
    node = DOC_NODE[dtype]
    other = db.scalars(select(m.Document).where(m.Document.application_id == doc.application_id,
                                                m.Document.id != doc.id, m.Document.node_id == node)).first()
    if other:
        if strict: raise DomainError(409, f"This application already has a {dtype.replace('_', ' ')} document ({other.id}); upload as a new version of it instead")
        return False
    doc.doc_type, doc.node_id, doc.type_confirmed = dtype, node, confirmed
    return True


def process_version(db: Session, app: m.Application, doc: m.Document, ver: m.DocumentVersion, *, use_llm: bool = True, client=None) -> dict:
    ver.processing_status = "extracting"
    diags = [d for d in (ver.diagnostics or []) if d.get("code") == "duplicate_file"]
    info = dict(claims_created=0, mode=None, needs_type_confirmation=False)
    try: data = Path(ver.storage_path).read_bytes()
    except Exception as e:
        ver.processing_status = "failed"
        ver.diagnostics = diags + [finding("error", "file_unreadable", f"Stored file unreadable: {e}")]
        return info
    ex = extract_pdf(data)
    diags += ex.diagnostics; ver.page_count = ex.page_count; ver.extracted_pages = ex.pages
    if ex.failed: ver.processing_status = "failed"; ver.diagnostics = diags; return info
    if ex.needs_ocr: ver.processing_status = "needs_ocr"; ver.diagnostics = diags; return info
    full = "\n".join(p["text"] for p in ex.pages)
    if not doc.type_confirmed and doc.doc_type == "unknown":
        dtype, conf = tu.classify_document(full)
        if dtype != "unknown" and conf >= 0.75:
            if assign_type(db, doc, dtype, confirmed=False, strict=False):
                diags.append(finding("info", "type_auto_classified", f"Classified as {dtype} (keyword confidence {conf}); please confirm."))
            else:
                diags.append(finding("warning", "type_conflict", f"Looks like a {dtype} but the application already has one; confirm the type or upload as a new version."))
        else:
            diags.append(finding("warning", "type_uncertain", "Document type could not be determined confidently; please confirm it."))
    if doc.doc_type == "unknown":
        ver.processing_status = "review_required"; ver.diagnostics = diags; info["needs_type_confirmation"] = True
        return info
    ver.diagnostics = diags  # (re-assigned below)
    diags += integrity.check_pages(ex.pages, doc.doc_type)
    if tu.normalize_ws(app.company_name) not in tu.normalize_ws(full):
        diags.append(finding("warning", "entity_name_not_found", f"Company name '{app.company_name}' was not found in the document text; check the entity."))
    res = map_claims(ex.pages, doc.doc_type, use_llm=use_llm, api_key=settings.anthropic_api_key, model=settings.anthropic_model, client=client)
    diags += res.diagnostics
    previous = {c.claim_type: c for c in current_claims(db, app.id) if c.source_document_id == doc.id}
    for c in previous.values(): c.is_current = False       # preserved, flagged superseded
    mode = res.mode if res.mode != "deterministic_fallback" else "deterministic_fallback"
    for a in res.accepted:
        c = a.cand
        row = m.Claim(application_id=app.id, entity_id=app.entity_id, node_id=NODE_FOR_CLAIM_TYPE[c.claim_type],
                      claim_type=c.claim_type, value=a.value_lakh, currency=c.currency, unit=a.unit_out,
                      period_start=c.period_start, period_end=c.period_end, source_document_id=doc.id,
                      document_version_id=ver.id, page_number=c.page_number, source_excerpt=c.source_excerpt,
                      bbox=c.bbox.model_dump() if c.bbox else None, confidence=c.confidence, extraction_mode=mode,
                      verification_status="pending_review", supersedes_claim_id=previous[c.claim_type].id if c.claim_type in previous else None)
        db.add(row)
    db.flush()
    periods = [a.cand.period_start for a in res.accepted if a.cand.period_start]
    ver.reporting_period = f"{periods[0]}/{res.accepted[0].cand.period_end}" if periods else None
    ver.extraction_mode = mode
    ver.processing_status = "review_required"
    if not res.accepted: diags.append(finding("warning", "no_claims_extracted", "No claims could be extracted; review the document manually."))
    ver.diagnostics = list(diags)
    info.update(claims_created=len(res.accepted), mode=mode)
    return info


def upload(db: Session, app: m.Application, filename: str, data: bytes, *, document: Optional[m.Document] = None,
           actor: str = "analyst", use_llm: bool = True, client=None) -> dict:
    validate_upload(filename, data)
    h: dict = {}
    def mutate():
        if document is None: doc, ver = create_document(db, app, filename, data)
        else: doc, ver = document, add_version(db, document, filename, data)
        h.update(doc=doc, ver=ver, info=process_version(db, app, doc, ver, use_llm=use_llm, client=client))
    cascade = apply_change(db, app, initiator=lambda: doc_node(h["doc"]) or h["doc"].id,
                           event_type="document_version_added" if document else "document_uploaded", actor=actor,
                           reason=lambda: f"Uploaded {h['ver'].original_filename} as {h['doc'].id} v{h['ver'].version_number}",
                           prev=None, new=lambda: {"document_id": h["doc"].id, "version_id": h["ver"].id, "claims_created": h["info"]["claims_created"]},
                           mutate=mutate, version_ids=lambda: [h["ver"].id])
    doc, ver = h["doc"], h["ver"]
    db.refresh(doc)
    diff = None
    if ver.version_number > 1:
        prev = db.scalars(select(m.DocumentVersion).where(m.DocumentVersion.document_id == doc.id,
                          m.DocumentVersion.version_number == ver.version_number - 1)).first()
        diff = version_diff(db, app, doc, prev.id, ver.id)
    return dict(document=doc, extraction_mode=h["info"]["mode"], warnings=[d for d in ver.diagnostics if d["level"] != "info"],
                claims_created=h["info"]["claims_created"], needs_type_confirmation=h["info"]["needs_type_confirmation"],
                cascade=cascade, diff=diff)


def _fmt(v) -> Optional[str]: return format(Decimal(v).normalize(), "f") if v is not None else None


def version_diff(db, app, doc, old_id: str, new_id: str) -> dict:
    def by_type(vid):
        rows = db.scalars(select(m.Claim).where(m.Claim.document_version_id == vid).order_by(m.Claim.created_at, m.Claim.id)).all()
        return {c.claim_type: c for c in rows}
    old, new = by_type(old_id), by_type(new_id)
    items, changed_nodes = [], set()
    for t in sorted(set(old) | set(new)):
        o, n = _fmt(old[t].value) if t in old else None, _fmt(new[t].value) if t in new else None
        items.append(dict(claim_type=t, old_value=o, new_value=n, changed=o != n))
        if o != n and t in NODE_FOR_CLAIM_TYPE:
            changed_nodes.add(NODE_FOR_CLAIM_TYPE[t])
    g = load_engine(db, app).g
    affected = set(changed_nodes)
    for n in changed_nodes:
        if n in g: affected |= nx.descendants(g, n)
    return dict(document_id=doc.id, old_version_id=old_id, new_version_id=new_id, items=items,
                affected_node_ids=[n for n in nx.topological_sort(g) if n in affected])
