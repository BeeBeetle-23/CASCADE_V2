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

export type DocumentType =
  | "bank_statement"
  | "income_tax_return"
  | "profit_and_loss"
  | "unknown";

export type DocumentDiagnostic = {
  level: string;
  code: string;
  message: string;
  page?: number;
};

export type DocumentVersionOut = {
  id: string;
  document_id: string;
  version_number: number;
  original_filename: string;
  file_hash: string;
  uploaded_at: string;
  processing_status: string;
  verification_status: string;
  reporting_period: string | null;
  is_current: boolean;
  page_count: number | null;
  diagnostics: DocumentDiagnostic[];
  extraction_mode: string | null;
};

export type DocumentOut = {
  id: string;
  application_id: string;
  doc_type: DocumentType;
  type_confirmed: boolean;
  created_at: string;
  versions: DocumentVersionOut[];
};

export type VersionDiffItem = {
  claim_type: string;
  old_value: string | null;
  new_value: string | null;
  changed: boolean;
};

export type VersionDiff = {
  document_id: string;
  old_version_id: string;
  new_version_id: string;
  items: VersionDiffItem[];
  affected_node_ids: string[];
};

export type UploadWarning = {
  level: string;
  code: string;
  message: string;
  [key: string]: unknown;
};

export type UploadResult = {
  document: DocumentOut;
  extraction_mode: "llm_mapped" | "deterministic_fallback" | null;
  claims_created: number;
  warnings: UploadWarning[];
  needs_type_confirmation: boolean;
  cascade: unknown;
  diff: VersionDiff | null;
};

export type ClaimOut = {
  id: string;
  application_id: string;
  entity_id: string;
  node_id: string;
  claim_type: string;
  value: string | number | null;
  currency: string;
  unit: string;
  period_start: string | null;
  period_end: string | null;
  source_document_id: string;
  document_version_id: string;
  page_number: number | null;
  source_excerpt: string | null;
  bbox: unknown;
  confidence: number | null;
  extraction_mode: string;
  verification_status: string;
  supersedes_claim_id: string | null;
  created_at: string;
  modified_at: string;
};

export type CreateApplicationBody = {
  company_name: string;
  requested_amount: number;
  currency?: string;
  reporting_period?: string;
};

