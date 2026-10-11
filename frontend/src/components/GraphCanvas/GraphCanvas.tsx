import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Calculator, FileText, Gauge, Gavel, Quote, Scale, SlidersHorizontal } from "lucide-react";
import type { GraphPayload, RFNodeData } from "../../types";
import { KIND_LABEL, TONE_CLASSES, recommendationLabel, statusLabel, toneOf } from "../../lib/status";

type FlowNode = Node<RFNodeData>;

const KIND_ICON: Record<string, typeof FileText> = {
  document: FileText,
  claim: Quote,
  adjustment: SlidersHorizontal,
  check: Scale,
  metric: Gauge,
  decision: Gavel,
};

function NodeCard({ data, selected }: NodeProps<FlowNode>) {
  const tone = TONE_CLASSES[toneOf(data.status)];
  const Icon = KIND_ICON[data.node_type] ?? Calculator;
  const dashed = data.status === "unverified" || data.status === "unavailable";
  const ring = data.initiator
    ? "ring-2 ring-trail ring-offset-2"
    : data.affected
      ? "ring-2 ring-trail/60 ring-offset-1"
      : selected
        ? "ring-2 ring-ink ring-offset-1"
        : "";
  return (
    <div
      className={`w-[220px] rounded-md border-l-4 border bg-panel px-3 py-2 text-left shadow-sm ${tone.border} ${
        dashed ? "border-dashed" : ""
      } ${ring}`}
      title={data.reason}
    >
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-1.5 text-xs text-ink-2">
        <Icon size={13} aria-hidden />
        <span>{KIND_LABEL[data.node_type] ?? data.node_type}</span>
        {data.initiator && <span className="ml-auto rounded bg-trail px-1.5 py-px font-medium text-white">Excluded</span>}
        {!data.initiator && data.affected && (
          <span className="ml-auto rounded bg-trail-soft px-1.5 py-px font-medium text-trail">Affected</span>
        )}
      </div>
      <div className="mt-0.5 text-sm font-semibold leading-snug text-ink">{data.label}</div>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className={`text-xs font-medium ${tone.text}`}>{statusLabel(data.status)}</span>
        {data.value !== null && (
          <span className="break-words text-right text-sm font-semibold text-ink">
            {data.node_type === "decision" ? recommendationLabel(data.value) : data.value}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

// The backend assigns a custom type per node kind; they all share one card.
const nodeTypes = {
  documentNode: NodeCard,
  claimNode: NodeCard,
  adjustmentNode: NodeCard,
  checkNode: NodeCard,
  metricNode: NodeCard,
  assessmentNode: NodeCard,
  recommendationNode: NodeCard,
};

const WIDE_LAYER = 6;
const ROW_GAP = 135;
const LAYER_GAP = 175;

/**
 * The backend lays each dependency layer out in a single row, which makes the 10-node evidence layer so wide
 * that fit-to-screen shrinks the text to an unreadable size. Wrap wide layers onto two staggered rows.
 * Order and x-spacing are preserved; only positions change.
 */
function relayout(nodes: GraphPayload["nodes"]): Record<string, { x: number; y: number }> {
  const layers = new Map<number, GraphPayload["nodes"]>();
  for (const n of nodes) layers.set(n.position.y, [...(layers.get(n.position.y) ?? []), n]);
  const pos: Record<string, { x: number; y: number }> = {};
  let y = 0;
  for (const key of [...layers.keys()].sort((a, b) => a - b)) {
    const row = layers.get(key)!.sort((a, b) => a.position.x - b.position.x);
    const rows = row.length > WIDE_LAYER ? 2 : 1;
    const per = Math.ceil(row.length / rows);
    for (let r = 0; r < rows; r++) {
      const chunk = row.slice(r * per, (r + 1) * per);
      const step = 260;
      chunk.forEach((n, i) => {
        pos[n.id] = { x: (i - (chunk.length - 1) / 2) * step + (rows > 1 && r === 1 ? step / 2 : 0), y: y + r * ROW_GAP };
      });
    }
    y += (rows - 1) * ROW_GAP + LAYER_GAP;
  }
  return pos;
}

type Props = {
  graph: GraphPayload;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  /** false renders a read-only view (used inside the simulation modal). */
  interactive?: boolean;
};

export function GraphCanvas({ graph, selectedId = null, onSelect, interactive = true }: Props) {
  const layout = useMemo(() => relayout(graph.nodes), [graph.nodes]);
  const nodes = useMemo<FlowNode[]>(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: layout[n.id] ?? n.position,
        data: n.data,
        selected: n.id === selectedId,
        draggable: false,
      })),
    [graph.nodes, layout, selectedId],
  );

  const edges = useMemo<Edge[]>(
    () =>
      graph.edges.map((e) => {
        const hot = !!e.data?.affected;
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: "smoothstep",
          animated: e.animated,
          label: e.label ?? undefined,
          markerEnd: { type: MarkerType.ArrowClosed, color: hot ? "#4b47d6" : "#9aa5b5" },
          style: { stroke: hot ? "#4b47d6" : "#b4bdca", strokeWidth: hot ? 2.25 : 1.25 },
        };
      }),
    [graph.edges],
  );

  return (
    <div className="h-full w-full" role="region" aria-label="Dependency graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.3}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={interactive}
        onNodeClick={interactive ? (_, node) => onSelect?.(node.id) : undefined}
        onPaneClick={interactive ? () => onSelect?.(null) : undefined}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d5dbe3" gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
