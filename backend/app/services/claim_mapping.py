"""Stages 2-3: map extracted text to candidate claims (LLM when configured, deterministic otherwise), then validate.
The LLM only proposes candidates; every candidate must pass code validation and still lands as pending_review."""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal as D
from typing import Any, Optional
from pydantic import ValidationError
from app.schemas.claim import ExtractedClaimCandidate
from . import text_utils as tu
from .integrity import finding

log = logging.getLogger("cascade.mapping")

DOC_CLAIM_TYPES = {
    "bank_statement": ["bank_inflow_total", "internal_transfer", "loan_proceeds", "refund_or_other_credit", "owner_equity_contribution"],
    "income_tax_return": ["gross_revenue_tax"],
    "profit_and_loss": ["gross_revenue_pnl", "cash_available_for_debt_service", "scheduled_debt_service",
                        "current_assets", "current_liabilities"],
}
LABELS = {  # deterministic label patterns per claim type
    "bank_inflow_total": r"total\s+(?:credits?|inflows?|deposits?)",
    "internal_transfer": r"(?:internal\s+transfers?|trf\s+(?:from|to)\s+own\s+a/c)",
    "loan_proceeds": r"(?:loan\s+(?:proceeds|disbursements?)|term\s+loan\s+disbursement)",
    "refund_or_other_credit": r"(?:refunds?(?:\s+or\s+other\s+credits?)?|gst\s+refund|refund\s+of\s+excess)",
    "owner_equity_contribution": r"(?:capital\s+infusion|equity\s+contribution|owner\s+equity|director\s+capital)",
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
    norm_fy = tu.normalize_period(full)
    out = []
    MULTI_TYPES = {"internal_transfer", "refund_or_other_credit", "loan_proceeds", "owner_equity_contribution"}
    for ctype in DOC_CLAIM_TYPES.get(doc_type, []):
        pat = re.compile(LABELS[ctype], re.I)
        for p in pages:
            lines = p["text"].splitlines()
            for idx, line in enumerate(lines):
                m = pat.search(line)
                if not m: continue
                # Search on line or adjacent window
                amts = tu.find_amounts(line[m.end():])
                if not amts and idx + 1 < len(lines):
                    amts = tu.find_amounts(lines[idx + 1])
                if amts:
                    v, u, _ = amts[0]; hit = (line.strip(), v, u or doc_unit or "INR")
                    line_val, v_val, u_val = hit
                    out.append(dict(claim_type=ctype, value=str(v_val), currency=cur, unit=u_val, page_number=p["page"],
                                    source_excerpt=line_val, bbox=_bbox_for(p, line_val), confidence=DETERMINISTIC_CONFIDENCE,
                                    period=norm_fy,
                                    period_start=fy[0].isoformat() if fy else None, period_end=fy[1].isoformat() if fy else None))
                    if ctype not in MULTI_TYPES:
                        break
            if ctype not in MULTI_TYPES and any(c["claim_type"] == ctype for c in out):
                break
    return out


# ---------- LLM ----------
SYSTEM = ("You extract candidate financial figures from document text. You do not calculate, judge, or infer. "
          "Return ONLY a JSON array, no prose and no markdown. Each item: claim_type, value (the number exactly as printed, "
          "digits only), currency (ISO code), unit (the unit word printed next to the number such as lakh or crore, "
          "or INR if raw rupees), period (standard FY label formatted as 'FYxxxx-yy', e.g. 'FY2025-26', derived from the document/transaction date), "
          "period_start/period_end (YYYY-MM-DD or null), page_number (integer from the page "
          "markers), source_excerpt (the exact line copied verbatim from the text), confidence (0-1). "
          "IMPORTANT: For bank statements, list ALL non-operating credit transactions individually as separate candidates "
          "(every internal transfer, every loan disbursement/proceed, every tax/vendor refund, and every owner/director equity/capital contribution), "
          "not just the first one. Only include figures that are explicitly present. If a figure is absent, omit it.")


def _llm_error(e: Exception, retries: int = 0) -> LLMError:
    n = type(e).__name__
    s = str(e).lower()
    code = getattr(e, "code", None)
    status = getattr(e, "status", None)
    message = getattr(e, "message", None) or str(e)
    log.error("Gemini call failed: code=%s status=%s message=%s", code, status, message)

    retry_suffix = f" after {retries} retries" if retries > 0 else ""
    parts = [str(p) for p in (code, status) if p]
    prefix = " ".join(parts)
    err_body = f"{prefix}: {message}" if prefix else (f"({n}): {message}" if message else f"({n})")
    err_detail = f"Gemini API error {err_body}{retry_suffix}"[:300]

    if n in ("RateLimitError", "ResourceExhausted") or "rate limit" in s or "resource_exhausted" in s or "429" in s:
        return LLMError("llm_rate_limited", f"Gemini API rate limit reached{retry_suffix}.")
    if n in ("APITimeoutError", "Timeout", "ReadTimeout", "DeadlineExceeded", "TimeoutException") or "timeout" in s or "deadline" in s:
        return LLMError("llm_timeout", f"Gemini API request timed out{retry_suffix}.")
    if (
        n in ("AuthenticationError", "PermissionDeniedError", "PermissionDenied", "Unauthenticated")
        or "api key" in s
        or "authentication" in s
        or "permission" in s
        or ("invalid_argument" in s and "key" in s)
        or "401" in s
        or "403" in s
    ):
        return LLMError("llm_auth", f"Gemini API key rejected{retry_suffix}.")
    if n in ("APIConnectionError", "ConnectionError") or "connection" in s:
        return LLMError("llm_unreachable", f"Could not reach the Gemini API{retry_suffix}.")
    return LLMError("llm_error", err_detail)


def llm_extract(pages: list[dict], doc_type: str, *, api_key: Optional[str], model: str, client: Any = None) -> list[dict]:
    if client is None:
        if not api_key: raise LLMError("llm_not_configured", "GEMINI_API_KEY is not set.")
        try:
            from google import genai
            from google.genai import types
        except ImportError: raise LLMError("llm_sdk_missing", "The 'google-genai' package is not installed.")
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120000))
    body = "\n".join(f"=== PAGE {p['page']} ===\n{p['text']}" for p in pages)[:60000]
    user = f"Document type: {doc_type}\nAllowed claim_type values: {DOC_CLAIM_TYPES[doc_type]}\n\n{body}"

    def _call_model(target_model: str) -> str:
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            from google.genai import types, errors
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_schema=list[ExtractedClaimCandidate],
                temperature=0.1,
            )

            backoffs = [2, 5, 10]
            max_retries = len(backoffs)
            for attempt in range(max_retries + 1):
                try:
                    resp = client.models.generate_content(model=target_model, contents=user, config=config)
                    return getattr(resp, "text", "") or ""
                except errors.ClientError:
                    raise
                except errors.ServerError as e:
                    if attempt < max_retries:
                        sleep_s = backoffs[attempt]
                        log.warning(
                            "Gemini model=%s attempt %d/%d failed with %s; retrying in %ds",
                            target_model, attempt + 1, max_retries, e, sleep_s,
                        )
                        time.sleep(sleep_s)
                        continue
                    raise
                except Exception as e:
                    s_lower = str(e).lower()
                    is_timeout = type(e).__name__ in ("APITimeoutError", "Timeout", "ReadTimeout", "DeadlineExceeded", "TimeoutException") or "timeout" in s_lower or "deadline" in s_lower
                    if is_timeout and attempt < max_retries:
                        sleep_s = backoffs[attempt]
                        log.warning(
                            "Gemini model=%s attempt %d/%d timed out with %s; retrying in %ds",
                            target_model, attempt + 1, max_retries, e, sleep_s,
                        )
                        time.sleep(sleep_s)
                        continue
                    raise
        elif hasattr(client, "messages") and hasattr(client.messages, "create"):
            resp = client.messages.create(model=target_model, max_tokens=2000, system=SYSTEM, messages=[{"role": "user", "content": user}])
            return "".join(getattr(b, "text", "") for b in getattr(resp, "content", [])).strip() if hasattr(resp, "content") else (getattr(resp, "text", "") or "")
        else:
            resp = client(model=target_model, contents=user)
            return getattr(resp, "text", str(resp))

    from app.core.config import settings
    fallback_model = settings.gemini_fallback_model

    try:
        text = _call_model(model)
    except Exception as primary_exc:
        from google.genai import errors
        is_client_error = isinstance(primary_exc, errors.ClientError)
        retries_count = 0 if is_client_error else (3 if hasattr(client, "models") and hasattr(client.models, "generate_content") else 0)
        if not is_client_error and fallback_model and fallback_model != model:
            log.warning("Primary model %s failed, attempting fallback model %s once", model, fallback_model)
            try:
                text = _call_model(fallback_model)
            except Exception as fb_exc:
                raise _llm_error(fb_exc, retries=retries_count) from fb_exc
        else:
            raise _llm_error(primary_exc, retries=retries_count) from primary_exc

    text = text.strip()
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
    
    MULTI_TYPES = {"internal_transfer", "refund_or_other_credit", "loan_proceeds", "owner_equity_contribution"}
    multi_candidates: dict[str, list[tuple[ExtractedClaimCandidate, D, str]]] = {k: [] for k in MULTI_TYPES}

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

        if c.claim_type in MULTI_TYPES:
            multi_candidates[c.claim_type].append((c, norm[0], norm[1]))
            continue

        if c.claim_type in seen: reject("duplicate candidate for this claim type (kept the first)"); continue
        seen.add(c.claim_type)
        flags = []
        if c.confidence < 0.6: flags.append("low_confidence")
        if c.value < 0: flags.append("negative_value")
        accepted.append(Accepted(c, norm[0], norm[1], flags))

    # Process and sum multi-candidates into one claim per claim type
    for ctype, cands in multi_candidates.items():
        if not cands: continue
        total_value_lakh = sum((c[1] for c in cands), D(0))
        first_c = cands[0][0]
        excerpts = [f"[p.{c[0].page_number}] {c[0].source_excerpt}" for c in cands]
        combined_excerpt = "; ".join(excerpts)[:2000]
        # Keep lowest confidence or avg confidence
        avg_conf = sum(c[0].confidence for c in cands) / len(cands)
        p_start = min((c[0].period_start for c in cands if c[0].period_start), default=first_c.period_start)
        p_end = max((c[0].period_end for c in cands if c[0].period_end), default=first_c.period_end)

        agg_cand = ExtractedClaimCandidate(
            claim_type=ctype,
            value=total_value_lakh,
            currency=first_c.currency,
            unit="lakh",
            period=first_c.period,
            period_start=p_start,
            period_end=p_end,
            page_number=first_c.page_number,
            source_excerpt=first_c.source_excerpt,
            bbox=first_c.bbox,
            confidence=round(avg_conf, 2),
        )
        flags = []
        if avg_conf < 0.6: flags.append("low_confidence")
        if total_value_lakh < 0: flags.append("negative_value")
        accepted.append(Accepted(agg_cand, total_value_lakh, "lakh", flags))

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
        diags.append(finding("info", "llm_not_configured", "No GEMINI_API_KEY configured; used the deterministic parser (no LLM was called)."))
    acc, d = validate_candidates(deterministic_candidates(pages, doc_type), pages, doc_type)
    return MappingResult(acc, "deterministic_fallback", diags + d)
