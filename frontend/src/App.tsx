import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, X } from "lucide-react";
import { api } from "./api/client";
import type { DashboardSummary, GraphPayload, ScenarioKey, SimulationResult } from "./types";
import { isEvidence } from "./lib/status";
import { ControlBar } from "./components/ControlBar";
import { Dashboard } from "./components/Dashboard";
import { GraphCanvas } from "./components/GraphCanvas";
import { SimulationModal } from "./components/SimulationModal";

type Busy = "scenario" | "reset" | "simulate" | null;

export default function App() {
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [target, setTarget] = useState("doc_bank");
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const scenario: ScenarioKey = graph?.scenario_key ?? "A";
  const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

  const refreshSummary = useCallback(async (appId: string) => {
    setSummary(await api.getSummary(appId));
  }, []);

  const init = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const apps = await api.listApplications();
      if (apps.length === 0) throw new Error("The backend has no applications yet. Load a scenario to begin.");
      const g = await api.getGraph(apps[0].id);
      setGraph(g);
      await refreshSummary(g.application_id);
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }, [refreshSummary]);

  useEffect(() => {
    void init();
  }, [init]);

  const run = async (kind: Exclude<Busy, "simulate">, fn: () => Promise<GraphPayload>) => {
    setBusy(kind);
    setError(null);
    try {
      const g = await fn();
      setGraph(g);
      setSelectedId(null);
      await refreshSummary(g.application_id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };

  const simulate = async () => {
    if (!graph) return;
    setBusy("simulate");
    setError(null);
    try {
      setSimulation(await api.simulate(graph.application_id, target));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };

  const select = (id: string | null) => {
    setSelectedId(id);
    const node = graph?.nodes.find((n) => n.id === id);
    if (node && isEvidence(node.data.node_type)) setTarget(node.id);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-2" role="status">
        <Loader2 className="animate-spin" size={18} aria-hidden /> Loading application…
      </div>
    );
  }

  if (!graph) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <AlertCircle className="text-bad" aria-hidden />
        <p className="max-w-md text-sm">{error}</p>
        <p className="max-w-md text-sm text-ink-2">
          Start the API with <code>uvicorn app.main:app --port 8000</code> from the backend folder, then try again.
        </p>
        <button onClick={() => void init()} className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <ControlBar
        scenario={scenario}
        nodes={graph.nodes}
        target={target}
        busy={busy}
        onScenario={(k) => void run("scenario", () => api.loadScenario(k))}
        onReset={() => void run("reset", () => api.reset(scenario))}
        onTarget={setTarget}
        onSimulate={() => void simulate()}
      />

      {error && (
        <div role="alert" className="flex items-center gap-2 border-b border-bad/30 bg-bad-soft px-5 py-2 text-sm text-bad">
          <AlertCircle size={15} aria-hidden />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss error" className="rounded p-0.5 hover:bg-bad/10">
            <X size={14} />
          </button>
        </div>
      )}

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <Dashboard summary={summary} graph={graph} selectedId={selectedId} />
        <div className="min-h-[480px] flex-1">
          <GraphCanvas graph={graph} selectedId={selectedId} onSelect={select} />
        </div>
      </main>

      {simulation && <SimulationModal result={simulation} live={graph} onClose={() => setSimulation(null)} />}
    </div>
  );
}
