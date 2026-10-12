import { useCallback, useEffect, useState } from "react";
import { AlertCircle, FileUp, Loader2, X } from "lucide-react";
import { api } from "./api/client";
import type { ApplicationSummary, DashboardSummary, GraphPayload, ScenarioKey, SimulationResult } from "./types";
import { isEvidence } from "./lib/status";
import { ControlBar, type CustomScenarioTab } from "./components/ControlBar";
import { Dashboard } from "./components/Dashboard";
import { GraphCanvas } from "./components/GraphCanvas";
import { DeleteScenarioModal } from "./components/DeleteScenarioModal";
import { NewScenarioModal } from "./components/NewScenarioModal";
import { SimulationModal } from "./components/SimulationModal";
import { UploadPanel } from "./components/UploadPanel";

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
  const [customApps, setCustomApps] = useState<ApplicationSummary[]>([]);
  const [activeTabKey, setActiveTabKey] = useState<string>("A");
  const [showNewModal, setShowNewModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

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
      setCustomApps(apps.slice(1));
      const g = await api.getGraph(apps[0].id);
      setGraph(g);
      setActiveTabKey(g.scenario_key ?? "A");
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

  const selectCustom = async (appId: string) => {
    setActiveTabKey(appId);
    setBusy("scenario");
    setError(null);
    try {
      const g = await api.getGraph(appId);
      setGraph(g);
      setSelectedId(null);
      await refreshSummary(appId);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };

  const handleScenarioCreated = async (newApp: ApplicationSummary) => {
    setCustomApps((prev) => [...prev, newApp]);
    setActiveTabKey(newApp.id);
    setBusy("scenario");
    setError(null);
    try {
      const g = await api.getGraph(newApp.id);
      setGraph(g);
      setSelectedId(null);
      await refreshSummary(newApp.id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteScenario = async () => {
    if (!graph) return;
    const targetId = graph.application_id;
    await api.deleteApplication(targetId);
    setCustomApps((prev) => prev.filter((a) => a.id !== targetId));
    setShowDeleteModal(false);
    setActiveTabKey("A");
    void run("scenario", () => api.loadScenario("A"));
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

  const customTabs: CustomScenarioTab[] = customApps.map((app, i) => ({
    id: app.id,
    label: `Scenario ${String.fromCharCode(68 + i)}`,
    companyName: app.company_name,
  }));

  const isCustom = graph ? graph.scenario_key === null : false;
  const isEmptyCustom = isCustom && (summary?.application.document_count ?? 0) === 0;

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
        onScenario={(k) => {
          setActiveTabKey(k);
          void run("scenario", () => api.loadScenario(k));
        }}
        onReset={() => void run("reset", () => api.reset(scenario))}
        onTarget={setTarget}
        onSimulate={() => void simulate()}
        customTabs={customTabs}
        activeKey={activeTabKey}
        onNewScenario={() => setShowNewModal(true)}
        onSelectCustom={(id) => void selectCustom(id)}
        disableReset={isCustom}
        disableSimulate={isEmptyCustom}
        isCustom={isCustom}
        onDelete={() => setShowDeleteModal(true)}
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
        <Dashboard
          summary={summary}
          graph={graph}
          selectedId={selectedId}
          uploadSlot={
            isCustom && graph ? (
              <UploadPanel
                key={graph.application_id}
                appId={graph.application_id}
                disabled={busy !== null}
                onRefreshGraph={async () => {
                  const g = await api.getGraph(graph.application_id);
                  setGraph(g);
                  await refreshSummary(graph.application_id);
                }}
                onCascadeAccept={async () => {
                  const g = await api.getGraph(graph.application_id);
                  setGraph(g);
                  setSelectedId(null);
                  await refreshSummary(graph.application_id);
                }}
              />
            ) : undefined
          }
        />
        <div className="min-h-[480px] flex-1">
          {isEmptyCustom ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 bg-paper p-6 text-center">
              <FileUp size={40} className="text-muted" aria-hidden />
              <p className="max-w-md text-sm text-ink-2">
                No data yet. Drop PDFs into the panel on the left to build this graph.
              </p>
            </div>
          ) : (
            <GraphCanvas graph={graph} selectedId={selectedId} onSelect={select} />
          )}
        </div>
      </main>

      {simulation && <SimulationModal result={simulation} live={graph} onClose={() => setSimulation(null)} />}
      {showNewModal && (
        <NewScenarioModal
          onClose={() => setShowNewModal(false)}
          onSuccess={(app) => void handleScenarioCreated(app)}
        />
      )}
      {showDeleteModal && (
        <DeleteScenarioModal
          scenarioName={summary?.application.company_name ?? "this scenario"}
          onClose={() => setShowDeleteModal(false)}
          onConfirm={handleDeleteScenario}
        />
      )}
    </div>
  );
}

