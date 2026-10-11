/** Mirrors the backend Pydantic schemas (app/schemas/*). Decimal values are strings on the wire. */

export type ScenarioKey = "A" | "B" | "C";

export type NodeKind =
  | "document"
  | "claim"
  | "adjustment"
  | "check"
  | "metric"
  | "decision";

export type NodeStatus =
  | "valid"
  | "unverified"
  | "unsupported"
  | "unavailable"
  | "green"
  | "amber"
  | "red"
  | "complete"
  | "incomplete"
  | "current"
  | "needs_review"
  | "stale";

export type Recommendation =
  | "APPROVE_CANDIDATE_PENDING_REVIEW"
  | "REFER_FOR_REVIEW"
  | "DECLINE_PENDING_REVIEW";

export type NodeState = {
  status: NodeStatus | string;
  value: string | null;
  reason: string;
};

export type RFNodeData = {
  label: string;
  node_type: NodeKind | string;
  status: NodeStatus | string;
  value: string | null;
  reason: string;
  verification: string | null;
  upstream: string[];
  downstream: string[];
  supporting_claim_ids: string[];
  affected: boolean;
  initiator: boolean;
  last_recalculated_at: string | null;
};

export type RFNode = {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: RFNodeData;
};

export type RFEdgeData = {
  reason?: string;
  relationship?: string;
  affected?: boolean;
};

export type RFEdge = {
  id: string;
  source: string;
  target: string;
  label: string | null;
  animated: boolean;
  data: RFEdgeData;
};

export type GraphPayload = {
  application_id: string;
  scenario_key: ScenarioKey | null;
  nodes: RFNode[];
  edges: RFEdge[];
  recommendation: NodeState;
  generated_at: string;
};

export type NodeDiff = { before: NodeState; after: NodeState };

export type SimulationResult = {
  id: number | null;
  excluded_node_id: string;
  original_recommendation: NodeState;
  simulated_recommendation: NodeState;
  recommendation_changed: boolean;
  changes: Record<string, NodeDiff>;
  created_at: string | null;
  simulated_graph: GraphPayload | null;
};

export type ApplicationSummary = {
  id: string;
  company_name: string;
  requested_amount: string;
  currency: string;
  reporting_period: string;
  document_count: number;
  outstanding_review_items: number;
  recommendation: Recommendation | string | null;
  recommendation_status: string | null;
};

export type CheckSummary = { status: NodeStatus | string; explanation: string };
export type MetricSummary = { value: string | null; status: NodeStatus | string };

export type DashboardSummary = {
  application: ApplicationSummary;
  recommendation: NodeState;
  checks: Record<string, CheckSummary>;
  metrics: Record<string, MetricSummary>;
};

export type ApiErrorBody = { error: string; detail?: unknown };
