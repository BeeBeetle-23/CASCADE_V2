import { FlaskConical, Loader2, RotateCcw } from "lucide-react";
import type { RFNode, ScenarioKey } from "../../types";
import { KIND_LABEL, SCENARIOS, isEvidence } from "../../lib/status";

type Props = {
  scenario: ScenarioKey;
  nodes: RFNode[];
  target: string;
  busy: "scenario" | "reset" | "simulate" | null;
  onScenario: (key: ScenarioKey) => void;
  onReset: () => void;
  onTarget: (id: string) => void;
  onSimulate: () => void;
};

export function ControlBar({ scenario, nodes, target, busy, onScenario, onReset, onTarget, onSimulate }: Props) {
  const evidence = nodes.filter((n) => isEvidence(n.data.node_type));
  const disabled = busy !== null;
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-panel px-5 py-3">
      <h1 className="text-lg font-bold tracking-tight">CASCADE</h1>

      <div role="radiogroup" aria-label="Scenario" className="flex overflow-hidden rounded-md border border-line">
        {SCENARIOS.map((s) => {
          const active = s.key === scenario;
          return (
            <button
              key={s.key}
              role="radio"
              aria-checked={active}
              title={s.blurb}
              disabled={disabled}
              onClick={() => !active && onScenario(s.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${
                active ? "bg-ink text-white" : "bg-panel text-ink-2 hover:bg-paper"
              }`}
            >
              {busy === "scenario" && active && <Loader2 size={13} className="animate-spin" aria-hidden />}
              {s.title}
            </button>
          );
        })}
      </div>

      <button
        onClick={onReset}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy === "reset" ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <RotateCcw size={14} aria-hidden />}
        Reset scenario
      </button>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <label htmlFor="sim-target" className="text-sm text-ink-2">
          Exclude from evidence
        </label>
        <select
          id="sim-target"
          value={target}
          onChange={(e) => onTarget(e.target.value)}
          disabled={disabled}
          className="max-w-[16rem] rounded-md border border-line bg-panel px-2 py-1.5 text-sm"
        >
          {evidence.map((n) => (
            <option key={n.id} value={n.id}>
              {KIND_LABEL[n.data.node_type]}: {n.data.label}
            </option>
          ))}
        </select>
        <button
          onClick={onSimulate}
          disabled={disabled || !target}
          className="flex items-center gap-1.5 rounded-md bg-trail px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-trail/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === "simulate" ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <FlaskConical size={14} aria-hidden />}
          Run simulation
        </button>
      </div>
    </header>
  );
}
