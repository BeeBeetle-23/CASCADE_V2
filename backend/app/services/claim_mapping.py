"""Stages 2-3: map extracted text to candidate claims (LLM when configured, deterministic otherwise), then validate.
The LLM only proposes candidates; every candidate must pass code validation and still lands as pending_review."""
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal as D
from typing import Any, Optional
from pydantic import ValidationError
from app.schemas.claim import ExtractedClaimCandidate
from . import text_utils as tu
from .integrity import finding

log = logging.getLogger("cascade.mapping")

DOC_CLAIM_TYPES = {
    "bank_statement": ["bank_inflow_total", "internal_transfer", "loan_proceeds", "refund_or_other_credit"],
    "income_tax_return": ["gross_revenue_tax"],
    "profit_and_loss": ["gross_revenue_pnl", "cash_available_for_debt_service", "scheduled_debt_service",
                        "current_assets", "current_liabilities"],
}
LABELS = {  # deterministic label patterns per claim type
    "bank_inflow_total": r"total\s+(?:credits?|inflows?|deposits?)",
    "internal_transfer": r"internal\s+transfers?",
    "loan_proceeds": r"loan\s+(?:proceeds|disbursements?)",
    "refund_or_other_credit": r"refunds?(?:\s+or\s+other\s+credits?)?",
    "gross_revenue_tax": r"gross\s+(?:receipts|revenue|turnover)",
    "gross_revenue_pnl": r"(?:gross|total)\s+revenue",
    "cash_available_for_debt_service": r"cash\s+available\s+for\s+debt\s+service|cfads",
    "scheduled_debt_service": r"scheduled\s+(?:debt\s+service|principal\s+and\s+interest)",
    "current_assets": r"total\s+current\s+assets",
    "current_liabilities": r"total\s+current\s+liabilities",
}
DETERMINISTIC_CONFIDENCE = 0.6   # heuristic warning signal, not calibrated


class LLMError(Exception):
    def __init__(self, code: str, message: str): self.code, self.message = code, message; super().__init__(message)


@dataclass
class Accepted:
    cand: ExtractedClaimCandidate
    value_lakh: D
    unit_out: str
    flags: list[str] = field(default_factory=list)


@dataclass
class MappingResult:
    accepted: list[Accepted]
    mode: str                        # llm_mapped | deterministic_fallback
    diagnostics: list[dict]


# ---------- deterministic fallback ----------
def _bbox_for(page: dict, line: str) -> Optional[dict]:
    want = tu.normalize_ws(line)
    for b in page.get("blocks", []):
        if tu.normalize_ws(b["text"]) == want or want in tu.normalize_ws(b["text"]):
            x0, y0, x1, y1 = b["bbox"]; return dict(x0=x0, y0=y0, x1=x1, y1=y1)
    return None


def deterministic_candidates(pages: list[dict], doc_type: str) -> list[dict]:
    full = "\n".join(p["text"] for p in pages)
    doc_unit, cur = tu.detect_doc_unit(full), tu.detect_currency(full)
    fy = tu.detect_fy(full)
    out = []
    for ctype in DOC_CLAIM_TYPES.get(doc_type, []):
        pat = re.compile(LABELS[ctype], re.I)
        for p in pages:
            hit = None
            for line in p["text"].splitlines():
                m = pat.search(line)
                if not m: continue
                amts = tu.find_amounts(line[m.end():])
                if amts:
                    v, u, _ = amts[0]; hit = (line.strip(), v, u or doc_unit or "INR"); break
            if hit:
                line, v, u = hit
                out.append(dict(claim_type=ctype, value=str(v), currency=cur, unit=u, page_number=p["page"],
                                source_excerpt=line, bbox=_bbox_for(p, line), confidence=DETERMINISTIC_CONFIDENCE,
                                period_start=fy[0].isoformat() if fy else None, period_end=fy[1].isoformat() if fy else None))
                break
    return out


# ---------- LLM ----------
SYSTEM = ("You extract candidate financial figures from document text. You do not calculate, judge, or infer. "
          "Return ONLY a JSON array, no prose and no markdown. Each item: claim_type, value (the number exactly as printed, "
          "digits only), currency (ISO code), unit (the unit word printed next to the number such as lakh or crore, "
          "or INR if raw rupees), period_start/period_end (YYYY-MM-DD or null), page_number (integer from the page "
          "markers), source_excerpt (the exact line copied verbatim from the text), confidence (0-1). "
          "Only include figures that are explicitly present. If a figure is absent, omit it.")


def _llm_error(e: Exception) -> LLMError:
    n = type(e).__name__
    if n == "RateLimitError": return LLMError("llm_rate_limited", "Anthropic API rate limit reached.")
    if n in ("APITimeoutError", "Timeout", "ReadTimeout"): return LLMError("llm_timeout", "Anthropic API request timed out.")
    if n in ("AuthenticationError", "PermissionDeniedError"): return LLMError("llm_auth", "Anthropic API key rejected.")
    if n == "APIConnectionError": return LLMError("llm_unreachable", "Could not reach the Anthropic API.")
    return LLMError("llm_error", f"Anthropic API error ({n}).")


def llm_extract(pages: list[dict], doc_type: str, *, api_key: Optional[str], model: str, client: Any = None) -> list[dict]:
    if client is None:
        if not api_key: raise LLMError("llm_not_configured", "ANTHROPIC_API_KEY is not set.")
        try: import anthropic
        except ImportError: raise LLMError("llm_sdk_missing", "The 'anthropic' package is not installed.")
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)
    body = "\n".join(f"=== PAGE {p['page']} ===\n{p['text']}" for p in pages)[:60000]
    user = f"Document type: {doc_type}\nAllowed claim_type values: {DOC_CLAIM_TYPES[doc_type]}\n\n{body}"
    try:
        resp = client.messages.create(model=model, max_tokens=2000, system=SYSTEM, messages=[{"role": "user", "content": user}])
    except Exception as e:
        raise _llm_error(e) from e
    text = "".join(getattr(b, "text", "") for b in resp.content).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try: data = json.loads(text)
    except json.JSONDecodeError: raise LLMError("llm_bad_response", "Model response was not valid JSON.")
    if isinstance(data, dict): data = data.get("claims", data.get("items"))
    if not isinstance(data, list): raise LLMError("llm_bad_response", "Model response was not a JSON array.")
    return data


# ---------- validation ----------
def validate_candidates(raw: list[Any], pages: list[dict], doc_type: str) -> tuple[list[Accepted], list[dict]]:
    accepted, diags, seen = [], [], set()
    allowed = set(DOC_CLAIM_TYPES.get(doc_type, []))
    page_text = {p["page"]: tu.normalize_ws(p["text"]) for p in pages}
    for item in raw:
        tag = item.get("claim_type", "?") if isinstance(item, dict) else "?"
        def reject(msg): diags.append(finding("warning", "claim_rejected", f"Rejected {tag}: {msg}", claim_type=tag))
        if not isinstance(item, dict): reject("not an object"); continue
        try: c = ExtractedClaimCandidate(**item)
        except (ValidationError, TypeError) as e:
            reject("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()) if isinstance(e, ValidationError) else str(e)); continue
        if c.claim_type not in allowed: reject(f"not valid for a {doc_type} document"); continue
        if c.page_number not in page_text: reject(f"page {c.page_number} does not exist"); continue
        if tu.normalize_ws(c.source_excerpt) not in page_text[c.page_number]:
            reject("source excerpt not found in the extracted text of that page"); continue
        printed = [a[0] for a in tu.find_amounts(c.source_excerpt)]
        if c.value not in printed: reject("value does not appear in the source excerpt"); continue
        norm = tu.to_lakh(c.value, c.unit, c.currency)
        if norm is None: reject(f"unsupported unit {c.unit!r}"); continue
        if c.claim_type in seen: reject("duplicate candidate for this claim type (kept the first)"); continue
        seen.add(c.claim_type)
        flags = []
        if c.confidence < 0.6: flags.append("low_confidence")
        if c.value < 0: flags.append("negative_value")
        accepted.append(Accepted(c, norm[0], norm[1], flags))
    for a in accepted:
        for f in a.flags:
            diags.append(finding("warning", f, f"{a.cand.claim_type}: flagged {f}; review before verifying.", claim_type=a.cand.claim_type))
    return accepted, diags


def map_claims(pages: list[dict], doc_type: str, *, use_llm: bool, api_key: Optional[str], model: str, client: Any = None) -> MappingResult:
    diags: list[dict] = []
    if use_llm and (client is not None or api_key):
        try:
            acc, d = validate_candidates(llm_extract(pages, doc_type, api_key=api_key, model=model, client=client), pages, doc_type)
            diags += d
            if acc: return MappingResult(acc, "llm_mapped", diags)
            diags.append(finding("warning", "llm_no_valid_claims", "LLM returned no claims that passed validation; used deterministic parser."))
        except LLMError as e:
            diags.append(finding("warning", e.code, f"{e.message} Falling back to the deterministic parser."))
    elif use_llm:
        diags.append(finding("info", "llm_not_configured", "No ANTHROPIC_API_KEY configured; used the deterministic parser (no LLM was called)."))
    acc, d = validate_candidates(deterministic_candidates(pages, doc_type), pages, doc_type)
    return MappingResult(acc, "deterministic_fallback", diags + d)
