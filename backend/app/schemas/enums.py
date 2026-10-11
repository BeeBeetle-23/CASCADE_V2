from enum import Enum


class DocumentType(str, Enum):
    bank_statement = "bank_statement"
    income_tax_return = "income_tax_return"
    profit_and_loss = "profit_and_loss"
    unknown = "unknown"  # classification uncertain: user must confirm


class ProcessingStatus(str, Enum):
    uploaded = "uploaded"
    extracting = "extracting"
    extracted = "extracted"
    needs_ocr = "needs_ocr"          # scanned / insufficient text; never fabricated
    review_required = "review_required"
    ready = "ready"
    failed = "failed"


class VerificationStatus(str, Enum):
    verified = "verified"
    unverified = "unverified"
    pending_review = "pending_review"


class ExtractionMode(str, Enum):
    """Provenance of a claim, so the UI never implies a live LLM ran when it did not."""
    pdf_extraction = "pdf_extraction"
    deterministic_fallback = "deterministic_fallback"
    llm_mapped = "llm_mapped"
    demo_fixture = "demo_fixture"
    manual_correction = "manual_correction"


class NodeType(str, Enum):
    document = "document"
    claim = "claim"
    adjustment = "adjustment"
    check = "check"
    metric = "metric"
    decision = "decision"


class NodeStatus(str, Enum):
    valid = "valid"
    unverified = "unverified"
    unsupported = "unsupported"
    unavailable = "unavailable"
    green = "green"
    amber = "amber"
    red = "red"
    complete = "complete"
    incomplete = "incomplete"
    current = "current"
    needs_review = "needs_review"
    stale = "stale"


class Recommendation(str, Enum):
    approve_candidate = "APPROVE_CANDIDATE_PENDING_REVIEW"
    refer = "REFER_FOR_REVIEW"
    decline_pending_review = "DECLINE_PENDING_REVIEW"


class AuditEventType(str, Enum):
    scenario_loaded = "scenario_loaded"
    verification_changed = "verification_changed"
    claim_corrected = "claim_corrected"
    document_uploaded = "document_uploaded"
    document_version_added = "document_version_added"
    document_processed = "document_processed"
    recalculated = "recalculated"
    simulation_run = "simulation_run"
    application_created = "application_created"
    document_type_confirmed = "document_type_confirmed"
    document_review_accepted = "document_review_accepted"
