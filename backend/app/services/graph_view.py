"""Adapts engine graph JSON to React Flow nodes/edges with deterministic layered positions."""
from datetime import datetime, timezone
import networkx as nx

RF_TYPE = {"document": "documentNode", "claim": "claimNode", "adjustment": "adjustmentNode",
           "check": "checkNode", "metric": "metricNode"}
X_STEP, Y_STEP = 260, 190


def to_reactflow(engine, application_id: str, affected=frozenset(), initiator: str | None = None,
                 state=None, support=None, recalculated: dict | None = None) -> dict:
    """`state` lets a simulated evaluation be rendered with the live layout."""
    g, st = engine.g, state or engine.state
    gens = list(nx.topological_generations(g))
    layer = {n: i for i, gen in enumerate(gens) for n in gen}
    # order within a layer by mean parent x to limit edge crossings; stable on ties
    xs: dict[str, float] = {}
    for gen in gens:
        ordered = sorted(gen, key=lambda n: (sum(xs[p] for p in g.predecessors(n)) / max(g.in_degree(n), 1)
                                              if g.in_degree(n) else 0, n))
        for i, n in enumerate(ordered):
            xs[n] = (i - (len(ordered) - 1) / 2) * X_STEP
    ts = datetime.now(timezone.utc).isoformat()
    nodes = []
    for n, d in g.nodes(data=True):
        rf = "recommendationNode" if n == "recommendation" else "assessmentNode" if d["type"] == "decision" else RF_TYPE[d["type"]]
        nodes.append(dict(id=n, type=rf, position=dict(x=xs[n], y=layer[n] * Y_STEP),
                          data=dict(label=d["label"], node_type=d["type"], status=st[n]["status"], value=st[n]["value"],
                                    reason=st[n]["reason"], verification=engine.verification.get(n),
                                    upstream=list(g.predecessors(n)), downstream=list(g.successors(n)),
                                    supporting_claim_ids=(support or {}).get(n, []), affected=n in affected, initiator=n == initiator,
                                    last_recalculated_at=(recalculated or {}).get(n, ts))))
    edges = [dict(id=f"{a}->{b}", source=a, target=b, animated=b in affected and (a in affected or a == initiator),
                  data=dict(reason=d["reason"], relationship="depends_on", affected=b in affected))
             for a, b, d in g.edges(data=True)]
    return dict(application_id=application_id, scenario_key=engine.scenario_key, nodes=nodes, edges=edges,
                recommendation=st["recommendation"], generated_at=ts)
