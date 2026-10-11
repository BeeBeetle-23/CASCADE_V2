"""Deterministic financial rules. Pure functions, no I/O, no LLM. Money is Decimal."""
from dataclasses import dataclass, field
from decimal import Decimal as D
from typing import Optional

ROUNDING_TOL = D("0.005")  # absolute rounding tolerance in the claim unit (lakh)


@dataclass(frozen=True)
class Basis:
    entity: str
    period: str
    currency: str
    unit: str
    concept: str = ""


def compatible(a: Basis, b: Basis, check_concept: bool = False) -> tuple[bool, str]:
    for f in ("entity", "period", "currency", "unit"):
        if getattr(a, f) != getattr(b, f):
            return False, f"incompatible {f}: {getattr(a, f)!r} vs {getattr(b, f)!r}"
    if check_concept and a.concept != b.concept:
        return False, f"different financial concept: {a.concept!r} vs {b.concept!r}"
    return True, "compatible"


def relative_discrepancy(a: D, b: D) -> D:
    """|a-b| / max(|a|,|b|). Zero vs zero -> 0. Zero vs nonzero -> 1 (fully discrepant)."""
    scale = max(abs(a), abs(b))
    return D(0) if scale == 0 else abs(a - b) / scale


@dataclass
class Reconciliation:
    status: str  # green | amber | red | unavailable
    residual: Optional[D] = None
    reported_difference: Optional[D] = None
    adjustments_total: Optional[D] = None
    relative_residual: Optional[D] = None
    over_reconciled: bool = False
    explanation: str = ""


def reconcile_revenue(bank: Optional[D], revenue: Optional[D], adjustments: list[D],
                      tolerance: D = D("0.02"), abs_min: D = D(0),
                      compat: tuple[bool, str] = (True, "")) -> Reconciliation:
    """residual = bank - revenue - verified non-revenue adjustments."""
    if bank is None or revenue is None:
        return Reconciliation("unavailable", explanation="Essential evidence missing; reconciliation not evaluated.")
    if not compat[0]:
        return Reconciliation("unavailable", explanation=f"Claims not comparable ({compat[1]}); rule not applied.")
    adj = sum(adjustments, D(0))
    diff = bank - revenue
    residual = diff - adj
    calc = f"{bank} - {revenue} - {adj} = {residual}"
    if residual < -ROUNDING_TOL:
        return Reconciliation("amber", residual, diff, adj, None, True,
                              f"Over-reconciled: adjustments exceed the gap by {-residual} ({calc}). "
                              "Recognized adjustments may be overstated or revenue understated; needs review.")
    if abs(residual) <= ROUNDING_TOL:
        return Reconciliation("green", D(0), diff, adj, D(0), False,
                              f"Fully explained: {calc}. Bank inflows exceed revenue only by recognized non-revenue credits.")
    rel = residual / abs(bank) if bank != 0 else D(1)
    material = rel > tolerance and residual > abs_min
    if material:
        return Reconciliation("red", residual, diff, adj, rel, False,
                              f"Material unexplained residual: {calc} ({rel:.2%} of inflows > {tolerance:.2%} threshold). "
                              "Requires human review; this is not a finding of fraud.")
    return Reconciliation("amber", residual, diff, adj, rel, False,
                          f"Limited residual: {calc} ({rel:.2%} <= {tolerance:.2%} threshold).")


@dataclass
class Contradiction:
    status: str  # green | red | unavailable
    difference: Optional[D] = None
    relative: Optional[D] = None
    explanation: str = ""


def compare_claims(a: Optional[D], b: Optional[D], compat: tuple[bool, str],
                   tolerance: D = D("0.02"), abs_min: D = D(0)) -> Contradiction:
    if a is None or b is None:
        return Contradiction("unavailable", explanation="One or both claims unavailable.")
    if not compat[0]:
        return Contradiction("unavailable", explanation=f"Claims not comparable ({compat[1]}).")
    diff = abs(a - b)
    rel = relative_discrepancy(a, b)
    if diff <= ROUNDING_TOL or (rel <= tolerance and diff <= max(abs_min, diff)):
        return Contradiction("green", diff, rel, f"Claims agree within tolerance ({a} vs {b}).")
    return Contradiction("red", diff, rel,
                         f"Material cross-document inconsistency: {a} vs {b} (difference {diff}, {rel:.2%} of the larger). "
                         "Neither document is presumed wrong.")


def dscr(cfads: Optional[D], debt_service: Optional[D]) -> tuple[Optional[D], str]:
    if cfads is None or debt_service is None:
        return None, "unavailable: missing input"
    if debt_service == 0:
        return None, "unavailable: scheduled debt service is zero"
    return (cfads / debt_service).quantize(D("0.01")), "ok"


def current_ratio(ca: Optional[D], cl: Optional[D]) -> tuple[Optional[D], str]:
    if ca is None or cl is None:
        return None, "unavailable: missing input"
    if ca < 0 or cl < 0:
        return None, "unavailable: negative input"
    if cl == 0:
        return None, "unavailable: current liabilities are zero"
    return (ca / cl).quantize(D("0.01")), "ok"


@dataclass
class Policy:
    min_dscr: D = D("1.25")
    min_current_ratio: D = D("1.00")
    decline_dscr: D = D("1.00")


def recommend(recon: str, contra: str, dscr_v: Optional[D], cr_v: Optional[D], policy: Policy = Policy()):
    """Returns (recommendation, reasons). Biased toward human review."""
    reasons = []
    if "unavailable" in (recon, contra) or dscr_v is None or cr_v is None:
        if recon == "unavailable": reasons.append("Revenue reconciliation lacks valid evidence.")
        if contra == "unavailable": reasons.append("Cross-document revenue comparison lacks valid evidence.")
        if dscr_v is None: reasons.append("DSCR unavailable.")
        if cr_v is None: reasons.append("Current ratio unavailable.")
        return "REFER_FOR_REVIEW", reasons
    if recon == "red": reasons.append("Material unexplained revenue/bank gap.")
    if contra == "red": reasons.append("Material cross-document revenue inconsistency.")
    if "amber" in (recon, contra): reasons.append("Reconciliation only partially explained.")
    if dscr_v < policy.decline_dscr:
        reasons.append(f"DSCR {dscr_v} below decline threshold {policy.decline_dscr}.")
        return "DECLINE_PENDING_REVIEW", reasons
    if dscr_v < policy.min_dscr: reasons.append(f"DSCR {dscr_v} below {policy.min_dscr}.")
    if cr_v < policy.min_current_ratio: reasons.append(f"Current ratio {cr_v} below {policy.min_current_ratio}.")
    if reasons:
        return "REFER_FOR_REVIEW", reasons
    return "APPROVE_CANDIDATE_PENDING_REVIEW", ["All checks green; DSCR and current ratio meet policy. Preliminary only."]
