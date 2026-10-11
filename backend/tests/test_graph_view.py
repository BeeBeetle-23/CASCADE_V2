import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from app.services.engine import Engine
from app.services.graph_view import to_reactflow


class GraphView(unittest.TestCase):
    def test_payload(self):
        e = Engine("A"); p = to_reactflow(e, "app_x")
        self.assertEqual(len(p["nodes"]), e.g.number_of_nodes()); self.assertEqual(len(p["edges"]), e.g.number_of_edges())
        pos = {n["id"]: n["position"] for n in p["nodes"]}
        for ed in p["edges"]:  # every edge points downward
            self.assertLess(pos[ed["source"]]["y"], pos[ed["target"]]["y"])
        self.assertEqual(len({(v["x"], v["y"]) for v in pos.values()}), len(pos))  # no overlaps
        self.assertTrue(all(ed["data"]["reason"] for ed in p["edges"]))
    def test_affected_flags(self):
        e = Engine("A"); r = e.set_verification("doc_bank", "unverified")
        p = to_reactflow(e, "a", affected=set(r["changed"]), initiator="doc_bank")
        d = {n["id"]: n["data"] for n in p["nodes"]}
        self.assertTrue(d["doc_bank"]["initiator"]); self.assertTrue(d["recommendation"]["affected"])
        self.assertFalse(d["m_dscr"]["affected"])

if __name__ == "__main__": unittest.main()
