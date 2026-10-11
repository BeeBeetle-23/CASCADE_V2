from typing import Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_app
from app.core.config import settings
from app.core.errors import DomainError
from app.db import models as m
from app.db.session import get_db
from app.schemas import (CascadeResult, DocumentOut, DocumentTypeConfirmRequest, DocumentVerifyRequest, VersionDiff)
from app.schemas.document import UploadResult
from app.services import ingestion, workflow
from app.services.state_store import record_audit

router = APIRouter(tags=["documents"])


async def _read(file: UploadFile) -> bytes:
    limit = settings.max_upload_mb * 1024 * 1024; buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf += chunk
        if len(buf) > limit: raise DomainError(413, f"File exceeds the {settings.max_upload_mb} MB limit")
    return bytes(buf)


@router.post("/applications/{application_id}/documents", response_model=UploadResult, status_code=201)
async def upload_document(file: UploadFile = File(...), actor: str = Form("analyst"), use_llm: bool = Form(True),
                          app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return ingestion.upload(db, app, file.filename or "", await _read(file), actor=actor, use_llm=use_llm)


@router.get("/applications/{application_id}/documents", response_model=list[DocumentOut])
def list_documents(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    docs = list(db.scalars(select(m.Document).where(m.Document.application_id == app.id).order_by(m.Document.created_at)))
    for d in docs: db.refresh(d)
    return docs


@router.post("/documents/{document_id}/versions", response_model=UploadResult, status_code=201)
async def upload_version(document_id: str, file: UploadFile = File(...), actor: str = Form("analyst"), use_llm: bool = Form(True),
                         db: Session = Depends(get_db)):
    doc = workflow.get_document(db, document_id)
    return ingestion.upload(db, db.get(m.Application, doc.application_id), file.filename or "", await _read(file),
                            document=doc, actor=actor, use_llm=use_llm)


@router.get("/documents/{document_id}/diff", response_model=VersionDiff)
def diff_versions(document_id: str, old: Optional[str] = None, new: Optional[str] = None, db: Session = Depends(get_db)):
    doc = workflow.get_document(db, document_id)
    vs = list(db.scalars(select(m.DocumentVersion).where(m.DocumentVersion.document_id == doc.id).order_by(m.DocumentVersion.version_number)))
    if len(vs) < 2 and not (old and new): raise DomainError(409, "Document has only one version")
    return ingestion.version_diff(db, db.get(m.Application, doc.application_id), doc, old or vs[-2].id, new or vs[-1].id)


@router.post("/documents/{document_id}/process", response_model=UploadResult)
def process_document(document_id: str, use_llm: bool = Query(True), db: Session = Depends(get_db)):
    """Re-run extraction/mapping on the current version (e.g. after confirming the type or adding an API key)."""
    doc = workflow.get_document(db, document_id); app = db.get(m.Application, doc.application_id)
    ver = ingestion.current_version(db, doc.id); h = {}
    def mutate(): h["info"] = ingestion.process_version(db, app, doc, ver, use_llm=use_llm)
    cascade = workflow.apply_change(db, app, initiator=lambda: ingestion.doc_node(doc) or doc.id, event_type="document_processed",
                                    actor="system", reason=f"Re-processed {doc.id} v{ver.version_number}", prev=None,
                                    new=lambda: {"claims_created": h["info"]["claims_created"], "mode": h["info"]["mode"]},
                                    mutate=mutate, version_ids=[ver.id])
    db.refresh(doc)
    return dict(document=doc, extraction_mode=h["info"]["mode"], warnings=[d for d in ver.diagnostics if d["level"] != "info"],
                claims_created=h["info"]["claims_created"], needs_type_confirmation=h["info"]["needs_type_confirmation"], cascade=cascade, diff=None)


@router.post("/documents/{document_id}/confirm-type", response_model=UploadResult)
def confirm_type(document_id: str, body: DocumentTypeConfirmRequest, db: Session = Depends(get_db)):
    doc = workflow.get_document(db, document_id)
    if body.doc_type.value == "unknown": raise DomainError(422, "Choose a concrete document type")
    ingestion.assign_type(db, doc, body.doc_type.value, confirmed=True, strict=True)
    app = db.get(m.Application, doc.application_id)
    record_audit(db, app.id, "document_type_confirmed", body.actor, doc.id, None, {"doc_type": doc.doc_type},
                 f"Document type confirmed as {doc.doc_type}", [], [], None, None)
    db.commit()
    return process_document(document_id, True, db)


@router.post("/documents/{document_id}/verify", response_model=CascadeResult)
def verify_document(document_id: str, body: DocumentVerifyRequest, db: Session = Depends(get_db)):
    return workflow.set_document_verification(db, document_id, body.status.value, body.actor, body.reason)


@router.post("/documents/{document_id}/review/accept", response_model=CascadeResult)
def accept_review(document_id: str, actor: str = Query("analyst"), db: Session = Depends(get_db)):
    return workflow.accept_review(db, document_id, actor)
