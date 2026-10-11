import { useEffect, useRef } from "react";
import { ArrowRight, X } from "lucide-react";
import type { GraphPayload, NodeState, SimulationResult } from "../../types";
import { TONE_CLASSES, recommendationLabel, recommendationTone, statusLabel } from "../../lib/status";
import { GraphCanvas } from "../GraphCanvas";
import { StatusBadge } from "../StatusBadge";

type Props = { result: SimulationResult; live: GraphPayload; onClose: () => void };

function Rec({ title, state }: { title: string; state: NodeState }) {
  const c = TONE_CLASSES[recommendationTone(state.value)];
  return (
    <div className={`flex-1 rounded-md border-l-4 p-3 ${c.bg} ${c.border}`}>
      <p className="text-xs text-ink-2">{title}</p>
      <p className={`text-base font-bold leading-tight ${c.text}`}>{recommendationLabel(state.value)}</p>
    </div>
  );
}

export function SimulationModal({ result, live, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const label = (id: string) => live.nodes.find((n) => n.id === id)?.data.label ?? id;
  const changes = Object.entries(result.changes);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sim-title"
        className="modal-in flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-lg bg-panel shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="sim-title" className="text-lg font-bold">
              What if “{label(result.excluded_node_id)}” is excluded?
            </h2>
            <p className="text-sm text-ink-2">
              This is a what-if run. Your live application and audit log are not changed.
            </p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close simulation"
            className="rounded p-1 text-ink-2 hover:bg-paper"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-0 overflow-y-auto lg:grid-cols-[380px_1fr] lg:overflow-hidden">
          <div className="flex flex-col gap-4 overflow-y-auto border-b border-line p-5 lg:border-b-0 lg:border-r">
            <div className="flex items-center gap-2">
              <Rec title="Live" state={result.original_recommendation} />
              <ArrowRight size={18} className="shrink-0 text-ink-2" aria-hidden />
              <Rec title="Without it" state={result.simulated_recommendation} />
            </div>
            <p
              className={`rounded-md px-3 py-2 text-sm font-semibold ${
                result.recommendation_changed ? "bg-trail-soft text-trail" : "bg-muted-soft text-ink-2"
              }`}
            >
              {result.recommendation_changed
                ? "The recommendation changes without this evidence."
                : "The recommendation stays the same without this evidence."}
            </p>
            <p className="text-sm text-ink-2">{result.simulated_recommendation.reason}</p>

            <div>
              <h3 className="text-sm font-semibold text-ink-2">
                {changes.length} {changes.length === 1 ? "node changes" : "nodes change"}
              </h3>
              <ul className="mt-1.5 flex flex-col gap-2">
                {changes.map(([id, d]) => (
                  <li key={id} className="rounded-md border border-line p-2.5">
                    <p className="text-sm font-semibold">{label(id)}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                      <StatusBadge status={d.before.status} />
                      <ArrowRight size={12} aria-hidden className="text-ink-2" />
                      <StatusBadge status={d.after.status} />
                      {(d.before.value !== d.after.value) && (
                        <span className="text-ink-2">
                          {d.before.value ?? "none"} → {d.after.value ?? "none"}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-ink-2">{statusLabel(d.after.status)}: {d.after.reason}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="h-[420px] bg-paper lg:h-auto lg:min-h-[480px]">
            {result.simulated_graph ? (
              <GraphCanvas graph={result.simulated_graph} interactive={false} />
            ) : (
              <p className="p-5 text-sm text-ink-2">The server didn't return a simulated graph.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
