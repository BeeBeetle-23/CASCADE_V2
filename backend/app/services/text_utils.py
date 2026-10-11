"""Pure text helpers (no pydantic/db): amounts, units, period and document-type detection."""
import re
from datetime import date
from decimal import Decimal as D, InvalidOperation
from typing import Optional

NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d])")
UNIT_AFTER = re.compile(r"^\s*(lakhs?|lacs?|crores?|cr)\b", re.I)
DOC_UNIT = re.compile(r"(?:in|amounts? in|figures? in|all amounts? in)\s*(?:₹|rs\.?|inr)?\s*(lakhs?|lacs?|crores?|rupees|inr)\b", re.I)
FY = re.compile(r"(?:\bFY|F\.Y\.?)\s*(\d{4})\s*[-–/]\s*(\d{2,4})", re.I)


def normalize_ws(s: str) -> str: return re.sub(r"\s+", " ", s).strip().lower()


def find_amounts(s: str) -> list[tuple[D, Optional[str], int]]:
    """[(value as printed, unit word or None, end index)]"""
    out = []
    for m in NUM.finditer(s):
        try: v = D(m.group(1).replace(",", ""))
        except InvalidOperation: continue
        if s[m.end():m.end() + 1] == "%": continue
        u = UNIT_AFTER.match(s[m.end():])
        out.append((v, u.group(1).lower() if u else None, m.end()))
    return out


def to_lakh(value: D, unit: str, currency: str = "INR") -> Optional[tuple[D, str]]:
    """Normalise a printed INR amount to lakh. Returns None when the unit is unsupported."""
    if currency.upper() != "INR": return (value, unit.lower())
    u = unit.lower().strip()
    if u in ("lakh", "lakhs", "lac", "lacs"): return (value, "lakh")
    if u in ("crore", "crores", "cr"): return (value * 100, "lakh")
    if u in ("inr", "rs", "rs.", "rupees", "₹", ""): return ((value / 100000), "lakh")
    return None


def detect_doc_unit(text: str) -> Optional[str]:
    m = DOC_UNIT.search(text)
    return m.group(1).lower() if m else None


def detect_fy(text: str) -> Optional[tuple[date, date]]:
    m = FY.search(text)
    if not m: return None
    y = int(m.group(1)); return date(y, 4, 1), date(y + 1, 3, 31)


def detect_currency(text: str) -> str:
    return "USD" if ("USD" in text or "$" in text) and "INR" not in text and "₹" not in text else "INR"


KEYWORDS = {
    "bank_statement": ["bank statement", "account statement", "opening balance", "closing balance", "withdrawal", "deposit", "narration", "total credits"],
    "income_tax_return": ["income tax return", "itr", "assessment year", "gross total income", "total income", "pan", "gross receipts"],
    "profit_and_loss": ["profit and loss", "profit & loss", "p&l", "net profit", "gross profit", "operating expenses", "gross revenue", "cost of goods"],
}


def classify_document(text: str) -> tuple[str, float]:
    t = normalize_ws(text)
    hits = {k: sum(1 for w in ws if re.search(r"\b" + re.escape(w) + r"\b", t)) for k, ws in KEYWORDS.items()}
    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    (top, th), (_, sh) = ranked[0], ranked[1]
    if th >= 2 and th >= sh + 1: return top, round(min(0.95, 0.5 + 0.15 * th - 0.1 * sh), 2)
    return "unknown", 0.3
