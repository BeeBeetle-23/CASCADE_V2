"""Document-integrity findings. Each finding states the observation and its evidence. No authenticity score;
metadata is reported as information only and never as proof of forgery."""
import re
from decimal import Decimal as D, InvalidOperation
from typing import Optional

EXPECTED_SECTIONS = {
    "bank_statement": ["opening balance", "closing balance"],
    "income_tax_return": ["assessment year", "total income"],
    "profit_and_loss": ["revenue", "expenses"],
}


def _num(cell) -> Optional[D]:
    c = re.sub(r"[₹,\s]|rs\.?|inr", "", str(cell or ""), flags=re.I)
    try: return D(c) if c else None
    except InvalidOperation: return None


def finding(level, code, message, **evidence): return dict(level=level, code=code, message=message, **evidence)


def check_pages(pages: list[dict], doc_type: str) -> list[dict]:
    out = []
    for p in pages:
        if len(p.get("text", "").strip()) < 5:
            out.append(finding("warning", "empty_page", f"Page {p['page']} has no extractable text.", page=p["page"]))
    text = " ".join(p.get("text", "") for p in pages).lower()
    for sec in EXPECTED_SECTIONS.get(doc_type, []):
        if sec not in text:
            out.append(finding("warning", "missing_section", f"Expected section/term '{sec}' not found in extracted text."))
    for p in pages:
        for ti, t in enumerate(p.get("tables", [])):
            out += check_table(t, p["page"], ti)
    return out


def check_table(rows: list[list], page: int, idx: int = 0) -> list[dict]:
    out, seen = [], {}
    for r in rows:
        key = tuple(str(c or "").strip() for c in r)
        if sum(1 for c in key if c) >= 3 and any(_num(c) is not None for c in key):
            seen[key] = seen.get(key, 0) + 1
    for key, n in seen.items():
        if n > 1:
            out.append(finding("warning", "duplicate_rows", f"Identical row appears {n} times in table {idx + 1}.",
                               page=page, evidence=list(key)))
    # arithmetic: a final row labelled 'total' vs the sum of numeric rows above, last column
    if len(rows) >= 3 and str(rows[-1][0] or "").strip().lower().startswith("total"):
        vals = [_num(r[-1]) for r in rows[:-1]]; tot = _num(rows[-1][-1])
        nums = [v for v in vals if v is not None]
        if tot is not None and len(nums) >= 2 and abs(sum(nums) - tot) > D("0.01"):
            out.append(finding("warning", "total_mismatch",
                               f"Table {idx + 1}: listed total {tot} differs from the sum of rows above ({sum(nums)}).",
                               page=page, listed_total=str(tot), computed_sum=str(sum(nums))))
    return out


def metadata_notes(meta: dict) -> list[dict]:
    """Informational only; metadata alone cannot establish authenticity or forgery."""
    keep = {k: v for k, v in (meta or {}).items() if v and k in ("creator", "producer", "creationDate", "modDate", "title")}
    if not keep: return []
    return [finding("info", "pdf_metadata", "PDF metadata recorded for reference; it does not establish authenticity.", metadata=keep)]
