"""NetworkX dependency graph + deterministic evaluation + cascade retraction + simulation.

The Engine can be built from the built-in demo scenarios or from database rows (values / verification / bases),
so the same deterministic rules drive both. Never LLM-driven."""
from datetime import datetime, timezone
from decimal import Decimal as D
from typing import Optional
import networkx as nx
from . import rules

BASIS = rules.Basis("alpha-tech-llc", "FY2025-26", "INR", "lakh")
TOLERANCE = D("0.02")

DOCS = {"doc_bank": "Bank statement", "doc_tax": "Income tax return", "doc_pnl": "P&L statement"}
CLAIMS = {  # node -> (label, source doc node, why the claim depends on the doc)
    "c_bank_inflow": ("Total comparable bank inflows", "doc_bank", "Extracted from bank statement credits"),
    "c_tax_rev": ("Tax return gross revenue", "doc_tax", "Reported on income tax return"),
    "c_pnl_rev": ("P&L gross revenue", "doc_pnl", "Reported on P&L statement"),
    "c_cfads": ("Cash available for debt service", "doc_pnl", "Reported in P&L / financial statements"),
    "c_ds": ("Scheduled principal + interest", "doc_pnl", "Reported in P&L / financial statements"),
    "c_ca": ("Current assets", "doc_pnl", "Reported in P&L / financial statements"),
    "c_cl": ("Current liabilities", "doc_pnl", "Reported in P&L / financial statements"),
}
ADJ = {"a_internal": "Verified internal transfers", "a_loan": "Verified loan proceeds",
       "a_refund": "Verified refunds / other non-revenue credits",
       "a_equity": "Verified owner / director equity contribution"}
ALL_CLAIM_NODES = set(CLAIMS) | set(ADJ)


def _scenario(name, bank=100, tax=80, pnl=80, adj=None):
    adj = {"internal": 12, "loan": 5, "refund": 3} if adj is None else adj
    return dict(name=name, bank=bank, tax=tax, pnl=pnl, adj=adj, cfads=30, ds=20, ca=60, cl=30)


SCENARIOS = {
    "A": _scenario("A: legitimate difference, fully reconciled"),
    "B": _scenario("B: hard contradiction (tax 80 vs P&L 60)", pnl=60),
    "C": _scenario("C: material unexplained gap", adj={"internal": 12, "loan": 5}),
}


def scenario_values(key: str) -> dict:
    s = SCENARIOS[key]
    v = {"c_bank_inflow": s["bank"], "c_tax_rev": s["tax"], "c_pnl_rev": s["pnl"], "c_cfads": s["cfads"],
         "c_ds": s["ds"], "c_ca": s["ca"], "c_cl": s["cl"]}
    v.update({f"a_{k}": x for k, x in s["adj"].items()})
    return {k: D(str(x)) for k, x in v.items()}


def now(): return datetime.now(timezone.utc).isoformat()
def fmt(d: D) -> str: return format(d.normalize(), "f")
ABSENT = {"status": "absent", "value": None, "reason": "Node did not exist before this change."}


class Engine:
    def __init__(self, scenario: Optional[str] = "A", policy=None, *, values=None, verification=None, bases=None):
        self.policy = policy or rules.Policy()
        self.audit: list[dict] = []
        self.scenario_key = scenario
        from_scenario = values is None
        if from_scenario:
            self.sc = SCENARIOS[scenario]
            values = scenario_values(scenario)
            verification = {n: "verified" for n in [*DOCS, *values]}
        else:
            self.sc = {"name": "Loaded from database"}
        self.values = {k: D(str(v)) for k, v in values.items()}
        self.verification = dict(verification or {})
        self.bases = dict(bases or {})
        self._build()
        self.state = self.evaluate()
        if from_scenario:
            self._log("scenario_loaded", "system", "demo", None, {"scenario": scenario},
                      f"Loaded scenario {self.sc['name']}", [], self.state)

    # ---------- construction (programmatic rules only; never LLM) ----------
    def _build(self):
        g = self.g = nx.DiGraph()
        def dep(a, b, why): g.add_edge(a, b, reason=why)
        for d, lab in DOCS.items(): g.add_node(d, type="document", label=lab)
        for n, (lab, doc, why) in CLAIMS.items():
            g.add_node(n, type="claim", label=lab); dep(doc, n, why)
        for n, lab in ADJ.items():
            if n in self.values:
                g.add_node(n, type="adjustment", label=lab)
                dep("doc_bank", n, "Non-revenue credit identified in bank statement")
        g.add_node("chk_recon", type="check", label="Revenue reconciliation (bank vs tax revenue)")
        for src in ["c_bank_inflow", "c_tax_rev"] + [a for a in ADJ if a in self.values]:
            dep(src, "chk_recon", "Input to residual = inflows - revenue - adjustments")
        g.add_node("chk_contra", type="check", label="Cross-document revenue consistency")
        dep("c_tax_rev", "chk_contra", "Compared claim"); dep("c_pnl_rev", "chk_contra", "Compared claim")
        g.add_node("m_dscr", type="metric", label="DSCR"); dep("c_cfads", "m_dscr", "Numerator"); dep("c_ds", "m_dscr", "Denominator")
        g.add_node("m_cr", type="metric", label="Current ratio"); dep("c_ca", "m_cr", "Numerator"); dep("c_cl", "m_cr", "Denominator")
        g.add_node("assessment", type="decision", label="Underwriting assessment")
        for s in ["chk_recon", "chk_contra", "m_dscr", "m_cr"]: dep(s, "assessment", "Required input to assessment")
        g.add_node("recommendation", type="decision", label="Preliminary recommendation")
        dep("assessment", "recommendation", "Recommendation derives from assessment")
        assert nx.is_directed_acyclic_graph(g), "dependency graph must be a DAG"

    # ---------- evaluation ----------
    def evaluate(self, excluded=frozenset()) -> dict:
        st = {}
        for n in nx.topological_sort(self.g):
            t = self.g.nodes[n]["type"]; parents = list(self.g.predecessors(n))
            if t == "document":
                v = self.verification.get(n, "missing")
                if v == "missing": st[n] = dict(status="unavailable", value=None, reason="No document of this type has been provided.")
                else:
                    ok = v == "verified" and n not in excluded
                    st[n] = dict(status="valid" if ok else "unverified", value=None,
                                 reason="Document verified." if ok else "Document unverified or excluded.")
            elif t in ("claim", "adjustment"):
                if n not in self.values:
                    st[n] = dict(status="unavailable", value=None, reason="No claim has been extracted for this input.")
                    continue
                own = self.verification.get(n, "unverified") == "verified" and n not in excluded
                doc_ok = st[parents[0]]["status"] == "valid"
                if own and doc_ok: s, r = "valid", "Supported by a verified source document."
                elif not own: s, r = "unverified", "Claim unverified, pending review, or excluded."
                else: s, r = "unsupported", f"Source {parents[0]} is not verified; claim has no valid support."
                st[n] = dict(status=s, value=fmt(self.values[n]), reason=r)
            else:
                st[n] = self._eval_derived(n, st)
        return st

    def _val(self, st, n):
        return self.values[n] if st.get(n, {}).get("status") == "valid" else None

    def _compat(self, nodes):
        base = self.bases.get(nodes[0], BASIS)
        for n in nodes[1:]:
            ok, msg = rules.compatible(base, self.bases.get(n, BASIS))
            if not ok: return False, f"{nodes[0]} vs {n}: {msg}"
        return True, "compatible"

    def _eval_derived(self, n, st):
        if n == "chk_recon":
            bank, rev = self._val(st, "c_bank_inflow"), self._val(st, "c_tax_rev")
            adj_nodes = [a for a in ADJ if a in self.values]
            valid_adj = [a for a in adj_nodes if st[a]["status"] == "valid"]
            compat = self._compat(["c_bank_inflow", "c_tax_rev", *valid_adj]) if bank is not None and rev is not None else (True, "")
            r = rules.reconcile_revenue(bank, rev, [self.values[a] for a in valid_adj], tolerance=TOLERANCE, compat=compat)
            if r.status == "unavailable":
                missing = [x for x in ["c_bank_inflow", "c_tax_rev"] if st[x]["status"] != "valid"]
                return dict(status="unavailable", value=None,
                            reason=r.explanation + (f" Missing valid: {', '.join(missing)}" if missing else ""))
            dropped = [a for a in adj_nodes if a not in valid_adj]
            extra = f" Excluded unsupported adjustments: {', '.join(dropped)}." if dropped else ""
            return dict(status=r.status, value=fmt(r.residual), reason=r.explanation + extra)
        if n == "chk_contra":
            a, b = self._val(st, "c_tax_rev"), self._val(st, "c_pnl_rev")
            compat = self._compat(["c_tax_rev", "c_pnl_rev"]) if a is not None and b is not None else (True, "")
            c = rules.compare_claims(a, b, compat, tolerance=TOLERANCE)
            return dict(status=c.status, value=fmt(c.difference) if c.difference is not None else None, reason=c.explanation)
        if n in ("m_dscr", "m_cr"):
            a, b = ("c_cfads", "c_ds") if n == "m_dscr" else ("c_ca", "c_cl")
            va, vb = self._val(st, a), self._val(st, b)
            v, msg = (rules.dscr if n == "m_dscr" else rules.current_ratio)(va, vb)
            return dict(status="valid" if v is not None else "unavailable", value=str(v) if v is not None else None,
                        reason=f"{self.g.nodes[n]['label']} = {fmt(va)} / {fmt(vb)}" if v is not None else msg)
        if n == "assessment":
            miss = [p for p in self.g.predecessors(n) if st[p]["status"] == "unavailable"]
            if miss: return dict(status="incomplete", value=None, reason=f"Required inputs unavailable: {', '.join(miss)}")
            return dict(status="complete", value=None, reason="All required inputs available.")
        if n == "recommendation":
            g = lambda x: st[x]["status"]
            v = lambda x: D(st[x]["value"]) if st[x]["value"] is not None and g(x) == "valid" else None
            rec, reasons = rules.recommend(g("chk_recon"), g("chk_contra"), v("m_dscr"), v("m_cr"), self.policy)
            if g("assessment") == "incomplete":
                return dict(status="needs_review", value="REFER_FOR_REVIEW",
                            reason="Previous recommendation is no longer current: " + " ".join(reasons))
            return dict(status="current", value=rec, reason=" ".join(reasons))

    def check_details(self) -> dict:
        st = self.state
        adj = [a for a in ADJ if a in self.values and st[a]["status"] == "valid"]
        bank, rev = self._val(st, "c_bank_inflow"), self._val(st, "c_tax_rev")
        both = bank is not None and rev is not None
        return {
            "chk_recon": dict(rule_type="revenue_reconciliation", compared=["c_bank_inflow", "c_tax_rev", *adj],
                              reported_difference=fmt(bank - rev) if both else None,
                              adjustments_total=fmt(sum((self.values[a] for a in adj), D(0))) if both else None,
                              residual=st["chk_recon"]["value"], threshold=str(TOLERANCE),
                              status=st["chk_recon"]["status"], explanation=st["chk_recon"]["reason"]),
            "chk_contra": dict(rule_type="cross_document_revenue", compared=["c_tax_rev", "c_pnl_rev"],
                               reported_difference=st["chk_contra"]["value"], adjustments_total=None, residual=None,
                               threshold=str(TOLERANCE), status=st["chk_contra"]["status"],
                               explanation=st["chk_contra"]["reason"]),
        }

    # ---------- audit / actions ----------
    def _log(self, typ, actor, target, prev, new, reason, affected, state):
        self.audit.append(dict(id=len(self.audit) + 1, type=typ, ts=now(), actor=actor, target=target, previous=prev,
                               new=new, reason=reason, affected=affected, recommendation=state["recommendation"]["value"]))

    @staticmethod
    def diff(before, after):
        return {n: dict(before=before.get(n, ABSENT), after=after[n]) for n in after
                if (before.get(n, ABSENT)["status"], before.get(n, ABSENT)["value"]) != (after[n]["status"], after[n]["value"])}

    def cascade_summary(self, initiator, before) -> dict:
        changes = self.diff(before, self.state)
        down = nx.descendants(self.g, initiator) if initiator in self.g else set()
        order = [n for n in nx.topological_sort(self.g) if n in down]
        return dict(initiator=initiator, downstream_order=order, changed=changes,
                    unchanged_downstream=[n for n in order if n not in changes],
                    independent_unchanged=[n for n in self.g if n not in down and n != initiator and n not in changes],
                    recommendation=self.state["recommendation"])

    def set_verification(self, node_id, status, actor="analyst", reason=""):
        assert status in ("verified", "unverified") and node_id in self.g
        before, prev = self.state, self.verification.get(node_id)
        self.verification[node_id] = status
        self.state = self.evaluate()
        s = self.cascade_summary(node_id, before)
        self._log("verification_changed", actor, node_id, prev, status, reason or f"{node_id} marked {status}",
                  [n for n in s["downstream_order"] if n in s["changed"]], self.state)
        return s

    def replace_claim(self, node_id, new_value, actor="analyst", reason="new document version"):
        before, old = self.state, self.values[node_id]
        self.values[node_id] = D(str(new_value)); self.state = self.evaluate()
        s = self.cascade_summary(node_id, before)
        self._log("claim_corrected", actor, node_id, fmt(old), fmt(self.values[node_id]), reason, list(s["changed"]), self.state)
        return s

    def simulate_without(self, node_id):
        """Counterfactual: temporary evaluation only; live state and audit untouched."""
        assert node_id in self.g, f"unknown node {node_id}"
        sim = self.evaluate(excluded=frozenset({node_id}))
        return dict(excluded=node_id, original=self.state["recommendation"], simulated=sim["recommendation"],
                    changes=self.diff(self.state, sim), state=sim)

    def graph_json(self):
        return dict(nodes=[dict(id=n, **self.g.nodes[n], **self.state[n], verification=self.verification.get(n),
                                upstream=list(self.g.predecessors(n)), downstream=list(self.g.successors(n)))
                           for n in nx.topological_sort(self.g)],
                    edges=[dict(source=a, target=b, reason=d["reason"]) for a, b, d in self.g.edges(data=True)])
