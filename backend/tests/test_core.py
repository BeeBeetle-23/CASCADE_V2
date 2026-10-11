import sys, pathlib, unittest
from decimal import Decimal as D
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from app.services import rules
from app.services.engine import Engine
OK = (True, "")


class Rules(unittest.TestCase):
    def test_scenario_a_green(self):
        r = rules.reconcile_revenue(D(100), D(80), [D(12), D(5), D(3)], compat=OK)
        self.assertEqual((r.status, r.residual), ("green", 0))
    def test_scenario_c_red(self):
        r = rules.reconcile_revenue(D(100), D(80), [D(12), D(5)], compat=OK)
        self.assertEqual((r.status, r.residual), ("red", 3))
    def test_amber_below_materiality(self):
        r = rules.reconcile_revenue(D(100), D(80), [D(12), D(5), D("2.5")], compat=OK)
        self.assertEqual(r.status, "amber")
    def test_over_reconciled_not_positive(self):
        r = rules.reconcile_revenue(D(100), D(80), [D(15), D(10)], compat=OK)
        self.assertTrue(r.over_reconciled); self.assertEqual(r.status, "amber"); self.assertLess(r.residual, 0)
    def test_rounding_tolerance(self):
        self.assertEqual(rules.reconcile_revenue(D(100), D(80), [D("19.999")], compat=OK).status, "green")
    def test_missing_not_zero(self):
        self.assertEqual(rules.reconcile_revenue(None, D(80), [], compat=OK).status, "unavailable")
    def test_incompatible_period_currency(self):
        a, b = rules.Basis("e", "FY25", "INR", "lakh"), rules.Basis("e", "FY24", "INR", "lakh")
        self.assertEqual(rules.reconcile_revenue(D(100), D(80), [], compat=rules.compatible(a, b)).status, "unavailable")
        c = rules.Basis("e", "FY25", "USD", "lakh")
        self.assertFalse(rules.compatible(a, c)[0])
        self.assertFalse(rules.compatible(a, rules.Basis("e", "FY25", "INR", "crore"))[0])
    def test_contradiction(self):
        self.assertEqual(rules.compare_claims(D(80), D(60), OK).status, "red")
        self.assertEqual(rules.compare_claims(D(80), D(80), OK).status, "green")
        self.assertEqual(rules.compare_claims(D(0), D(0), OK).status, "green")
        self.assertEqual(rules.compare_claims(D(0), D(5), OK).status, "red")
    def test_ratios(self):
        self.assertEqual(rules.dscr(D(30), D(20))[0], D("1.50"))
        self.assertIsNone(rules.dscr(D(30), D(0))[0]); self.assertIsNone(rules.dscr(None, D(1))[0])
        self.assertEqual(rules.current_ratio(D(60), D(30))[0], D("2.00"))
        self.assertIsNone(rules.current_ratio(D(60), D(0))[0])


class EngineTests(unittest.TestCase):
    def test_scenarios(self):
        a, b, c = Engine("A").state, Engine("B").state, Engine("C").state
        self.assertEqual(a["chk_recon"]["status"], "green"); self.assertEqual(a["recommendation"]["value"], "APPROVE_CANDIDATE_PENDING_REVIEW")
        self.assertEqual(b["chk_contra"]["status"], "red"); self.assertEqual(b["recommendation"]["value"], "REFER_FOR_REVIEW")
        self.assertEqual((c["chk_recon"]["status"], c["chk_recon"]["value"]), ("red", "3"))
    def test_dag(self):
        import networkx as nx
        self.assertTrue(nx.is_directed_acyclic_graph(Engine("A").g))
    def test_cascade_bank_unverified(self):
        e = Engine("A"); res = e.set_verification("doc_bank", "unverified")
        s = e.state
        self.assertEqual(s["chk_recon"]["status"], "unavailable")
        self.assertEqual(s["assessment"]["status"], "incomplete")
        self.assertEqual(s["recommendation"]["status"], "needs_review")
        for keep in ["m_dscr", "m_cr", "chk_contra", "c_tax_rev", "doc_tax"]:
            self.assertNotIn(keep, res["changed"]); 
        self.assertEqual(s["m_dscr"]["value"], "1.50")
        self.assertEqual(res["downstream_order"][-1], "recommendation")
        ev = e.audit[-1]; self.assertEqual(ev["type"], "verification_changed"); self.assertIn("chk_recon", ev["affected"])
    def test_restore_preserves_history(self):
        e = Engine("A"); e.set_verification("doc_bank", "unverified"); e.set_verification("doc_bank", "verified")
        self.assertEqual(e.state["recommendation"]["status"], "current")
        self.assertEqual([x["new"] for x in e.audit if x["type"] == "verification_changed"], ["unverified", "verified"])
    def test_single_adjustment_unverified_turns_red(self):
        e = Engine("A"); e.set_verification("a_refund", "unverified")
        self.assertEqual((e.state["chk_recon"]["status"], e.state["chk_recon"]["value"]), ("red", "3"))
    def test_independent_branch_cascade(self):
        e = Engine("A"); e.set_verification("doc_pnl", "unverified")
        self.assertEqual(e.state["chk_recon"]["status"], "green")  # bank + tax branch unaffected
        self.assertEqual(e.state["m_dscr"]["status"], "unavailable")
    def test_correction_preserves_old_value(self):
        e = Engine("B"); e.replace_claim("c_pnl_rev", 80)
        self.assertEqual(e.state["chk_contra"]["status"], "green")
        self.assertEqual(e.audit[-1]["previous"], "60")
    def test_simulation_does_not_mutate(self):
        e = Engine("A"); n_audit, snap = len(e.audit), dict(e.state)
        sim = e.simulate_without("doc_bank")
        self.assertEqual(sim["simulated"]["status"], "needs_review")
        self.assertEqual(e.state, snap); self.assertEqual(len(e.audit), n_audit)
        self.assertEqual(e.verification["doc_bank"], "verified")

if __name__ == "__main__": unittest.main()


class DbMode(unittest.TestCase):
    def test_missing_doc_and_claims_are_unavailable_not_zero(self):
        from app.services.engine import Engine as E
        e = E(None, values={}, verification={})
        for n in ["doc_bank", "c_bank_inflow", "chk_recon", "m_dscr"]:
            self.assertEqual(e.state[n]["status"], "unavailable")
        self.assertEqual(e.state["recommendation"]["status"], "needs_review")
    def test_incompatible_basis_blocks_reconciliation(self):
        from app.services.engine import Engine as E, scenario_values, BASIS
        from app.services import rules
        v = scenario_values("A"); ver = {n: "verified" for n in [*v, "doc_bank", "doc_tax", "doc_pnl"]}
        bases = {"c_tax_rev": rules.Basis(BASIS.entity, "FY2024-25", "INR", "lakh")}
        e = E(None, values=v, verification=ver, bases=bases)
        self.assertEqual(e.state["chk_recon"]["status"], "unavailable"); self.assertIn("incompatible period", e.state["chk_recon"]["reason"])
    def test_pending_claim_is_excluded_until_verified(self):
        from app.services.engine import Engine as E, scenario_values
        v = scenario_values("A"); ver = {n: "verified" for n in [*v, "doc_bank", "doc_tax", "doc_pnl"]}; ver["c_pnl_rev"] = "unverified"
        e = E(None, values=v, verification=ver)
        self.assertEqual(e.state["chk_contra"]["status"], "unavailable"); self.assertEqual(e.state["chk_recon"]["status"], "green")
    def test_check_details(self):
        d = Engine("C").check_details()["chk_recon"]
        self.assertEqual((d["residual"], d["reported_difference"], d["adjustments_total"]), ("3", "20", "17"))
