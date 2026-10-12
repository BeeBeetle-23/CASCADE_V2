from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from .common import BoundingBox, ORM
from .enums import ExtractionMode, VerificationStatus

ALLOWED_CLAIM_TYPES = {
    "bank_inflow_total", "internal_transfer", "loan_proceeds", "refund_or_other_credit",
    "owner_equity_contribution",
    "gross_revenue_tax", "gross_revenue_pnl", "cash_available_for_debt_service",
    "scheduled_debt_service", "current_assets", "current_liabilities",
}


class ClaimOut(ORM):
    id: str
    application_id: str
    entity_id: str
    node_id: str
    claim_type: str
    value: Optional[Decimal] = None
    currency: str
    unit: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    source_document_id: str
    document_version_id: str
    page_number: Optional[int] = None          # None = provenance unavailable (not zero)
    source_excerpt: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    confidence: Optional[float] = None         # model/heuristic warning signal, NOT calibrated
    extraction_mode: ExtractionMode
    verification_status: VerificationStatus
    supersedes_claim_id: Optional[str] = None
    created_at: datetime
    modified_at: datetime


class ClaimVerifyRequest(BaseModel):
    status: VerificationStatus
    reason: str = Field(default="", max_length=1000)
    actor: str = Field(default="analyst", max_length=100)


class ClaimCorrectionRequest(BaseModel):
    new_value: Decimal = Field(description="Corrected value in the claim's existing unit")
    reason: str = Field(min_length=3, max_length=1000)
    actor: str = Field(default="analyst", max_length=100)


class ExtractedClaimCandidate(BaseModel):
    """Constrained schema for LLM/fallback output. Validated before it can become a claim."""
    claim_type: str
    value: Decimal
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    unit: str = Field(min_length=1, max_length=20)
    period: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    page_number: int = Field(ge=1)
    source_excerpt: str = Field(min_length=1, max_length=2000)
    bbox: Optional[BoundingBox] = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check(self):
        if self.claim_type not in ALLOWED_CLAIM_TYPES:
            raise ValueError(f"unsupported claim_type {self.claim_type!r}")
        if self.period:
            import re
            from datetime import date as dt_date
            # Check for FY pattern: FY2025-26
            m_fy = re.search(r"FY(\d{4})", self.period, re.I)
            if m_fy:
                y = int(m_fy.group(1))
                if not self.period_start: self.period_start = dt_date(y, 4, 1)
                if not self.period_end: self.period_end = dt_date(y + 1, 3, 31)
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        self.currency = self.currency.upper()
        return self
