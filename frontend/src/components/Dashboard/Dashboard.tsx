import type { DashboardSummary, GraphPayload } from "../../types";
import { KIND_LABEL, TONE_CLASSES, recommendationLabel, recommendationTone, statusLabel, toneOf } from "../../lib/status";
import { StatusBadge } from "../StatusBadge";

type Props = { summary: DashboardSummary | null; graph: GraphPayload; selectedId: string | null };

const METRICS = [
  { id: "m_dscr", name: "DSCR", hint: "Cash available ÷ scheduled debt service" },
  { id: "m_cr", name: "Current ratio", hint: "Current assets ÷ current liabilities" },
];

export function Dashboard({ summary, graph, selectedId }: Props) {
  const label = (id: string) => graph.nodes.find((n) => n.id === id)?.data.label ?? id;
  const rec = summary?.recommendation ?? graph.recommendation;
  const recTone = TONE_CLASSES[recommendationTone(rec.value)];
  const selected = graph.nodes.find((n) => n.id === selectedId);

  return (
    <aside className="flex h-full w-full flex-col gap-6 overflow-y-auto border-r border-line bg-panel p-5 lg:w-[340px] lg:shrink-0">
      {summary && (
        <div>
          <h2 className="text-base font-semibold">{summary.application.company_name}</h2>
          <p className="text-sm text-ink-2">
            Requested {summary.application.requested_amount} lakh {summary.application.currency} for{" "}
            {summary.application.reporting_period}. {summary.application.document_count} documents on file.
          </p>
        </div>
      )}

      <section aria-labelledby="rec-h">
        <h2 id="rec-h" className="text-sm font-semibold text-ink-2">Recommendation</h2>
        <div className={`mt-1.5 rounded-md border-l-4 p-3 ${recTone.bg} ${recTone.border}`}>
          <p className={`text-lg font-bold leading-tight ${recTone.text}`}>{recommendationLabel(rec.value)}</p>
          <p className="mt-1 text-sm text-ink-2">{rec.reason}</p>
        </div>
      </section>

      <section aria-labelledby="met-h">
        <h2 id="met-h" className="text-sm font-semibold text-ink-2">Coverage metrics</h2>
        <div className="mt-1.5 grid grid-cols-2 gap-3">
          {METRICS.map((m) => {
            const v = summary?.metrics[m.id];
            return (
              <div key={m.id} className="rounded-md border border-line p-3" title={m.hint}>
                <p className="text-sm text-ink-2">{m.name}</p>
                <p className="text-2xl font-bold">{v?.value ? `${v.value}×` : "n/a"}</p>
                {v && <StatusBadge status={v.status} />}
              </div>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="chk-h">
        <h2 id="chk-h" className="text-sm font-semibold text-ink-2">Checks</h2>
        <ul className="mt-1.5 flex flex-col gap-3">
          {Object.entries(summary?.checks ?? {}).map(([id, c]) => (
            <li key={id} className="rounded-md border border-line p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold">{label(id)}</p>
                <StatusBadge status={c.status} />
              </div>
              <p className="mt-1 text-sm leading-relaxed text-ink-2">{c.explanation}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sel-h" aria-live="polite">
        <h2 id="sel-h" className="text-sm font-semibold text-ink-2">Selected node</h2>
        {selected ? (
          <div className="mt-1.5 rounded-md border border-line p-3">
            <p className="text-xs text-ink-2">{KIND_LABEL[selected.data.node_type] ?? selected.data.node_type}</p>
            <p className="text-sm font-semibold">{selected.data.label}</p>
            <p className={`mt-1 text-xs font-medium ${TONE_CLASSES[toneOf(selected.data.status)].text}`}>
              {statusLabel(selected.data.status)}
              {selected.data.value !== null && ` · ${selected.data.value}`}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{selected.data.reason}</p>
            {selected.data.upstream.length > 0 && (
              <p className="mt-2 text-xs text-ink-2">Depends on: {selected.data.upstream.map(label).join(", ")}</p>
            )}
            {selected.data.downstream.length > 0 && (
              <p className="mt-1 text-xs text-ink-2">Feeds: {selected.data.downstream.map(label).join(", ")}</p>
            )}
          </div>
        ) : (
          <p className="mt-1.5 text-sm text-ink-2">Select a node in the graph to see why it has its status.</p>
        )}
      </section>
    </aside>
  );
}
