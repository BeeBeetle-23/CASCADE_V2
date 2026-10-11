from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from .common import ORM
from .enums import DocumentType, ProcessingStatus, VerificationStatus


class DocumentVersionOut(ORM):
    id: str
    document_id: str
    version_number: int
    original_filename: str
    file_hash: str
    uploaded_at: datetime
    processing_status: ProcessingStatus
    verification_status: VerificationStatus
    reporting_period: Optional[str] = None
    is_current: bool
    page_count: Optional[int] = None
    diagnostics: list[dict[str, Any]] = []   # warnings/errors: {level, code, message, page?}
    extraction_mode: Optional[str] = None


class DocumentOut(ORM):
    id: str
    application_id: str
    doc_type: DocumentType
    type_confirmed: bool
    created_at: datetime
    versions: list[DocumentVersionOut] = []


class DocumentVerifyRequest(BaseModel):
    status: VerificationStatus
    reason: str = Field(default="", max_length=1000)
    actor: str = Field(default="analyst", max_length=100)


class DocumentTypeConfirmRequest(BaseModel):
    doc_type: DocumentType
    actor: str = Field(default="analyst", max_length=100)


class VersionDiffItem(BaseModel):
    claim_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed: bool


class VersionDiff(BaseModel):
    document_id: str
    old_version_id: str
    new_version_id: str
    items: list[VersionDiffItem]
    affected_node_ids: list[str] = []


from .simulation import CascadeResult  # noqa: E402


class UploadResult(BaseModel):
    document: DocumentOut
    extraction_mode: Optional[str] = None        # llm_mapped | deterministic_fallback | None (nothing extracted)
    claims_created: int = 0
    warnings: list[dict[str, Any]] = []
    needs_type_confirmation: bool = False
    cascade: CascadeResult
    diff: Optional[VersionDiff] = None
