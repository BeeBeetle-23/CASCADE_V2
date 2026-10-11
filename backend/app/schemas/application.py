from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from .common import ORM


class ApplicationCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    requested_amount: Decimal = Field(gt=0, description="Requested credit amount in the stated currency (lakh)")
    currency: str = Field(default="INR", pattern=r"^[A-Za-z]{3}$")
    reporting_period: str = Field(min_length=1, max_length=40, examples=["FY2025-26"])
    scenario: Optional[Literal["A", "B", "C"]] = None  # seed from a demo scenario

    @field_validator("currency")
    @classmethod
    def _upper(cls, v): return v.upper()

    @field_validator("company_name")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if not v: raise ValueError("company_name must not be blank")
        return v


class ApplicationOut(ORM):
    id: str
    company_name: str
    requested_amount: Decimal
    currency: str
    reporting_period: str
    scenario_key: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class ApplicationSummary(ApplicationOut):
    document_count: int
    outstanding_review_items: int
    recommendation: Optional[str] = None
    recommendation_status: Optional[str] = None
