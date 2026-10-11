import type { Recommendation } from "../types";

export type Tone = "good" | "warn" | "bad" | "muted";

const TONE: Record<string, Tone> = {
  valid: "good",
  green: "good",
  complete: "good",
  current: "good",
  amber: "warn",
  incomplete: "warn",
  needs_review: "warn",
  stale: "warn",
  red: "bad",
  unsupported: "bad",
  unverified: "muted",
  unavailable: "muted",
};

export const toneOf = (status: string): Tone => TONE[status] ?? "muted";

export const STATUS_LABEL: Record<string, string> = {
  valid: "Valid",
  green: "Passing",
  amber: "Needs a look",
  red: "Failing",
  complete: "Complete",
  incomplete: "Incomplete",
  current: "Current",
  needs_review: "Needs review",
  stale: "Stale",
  unverified: "Unverified",
  unsupported: "Unsupported",
  unavailable: "Unavailable",
};

export const statusLabel = (s: string) => STATUS_LABEL[s] ?? s.replace(/_/g, " ");

/** Tailwind class bundles per tone (kept literal so Tailwind can see them). */
export const TONE_CLASSES: Record<Tone, { text: string; bg: string; border: string; dot: string }> = {
  good: { text: "text-good", bg: "bg-good-soft", border: "border-good", dot: "bg-good" },
  warn: { text: "text-warn", bg: "bg-warn-soft", border: "border-warn", dot: "bg-warn" },
  bad: { text: "text-bad", bg: "bg-bad-soft", border: "border-bad", dot: "bg-bad" },
  muted: { text: "text-muted", bg: "bg-muted-soft", border: "border-muted", dot: "bg-muted" },
};

export const RECOMMENDATION_LABEL: Record<Recommendation, string> = {
  APPROVE_CANDIDATE_PENDING_REVIEW: "Approve, pending review",
  REFER_FOR_REVIEW: "Refer for review",
  DECLINE_PENDING_REVIEW: "Decline, pending review",
};

export const recommendationLabel = (v: string | null | undefined) =>
  v ? (RECOMMENDATION_LABEL as Record<string, string>)[v] ?? v.replace(/_/g, " ").toLowerCase() : "No recommendation";

export const recommendationTone = (v: string | null | undefined): Tone =>
  v === "APPROVE_CANDIDATE_PENDING_REVIEW" ? "good" : v === "DECLINE_PENDING_REVIEW" ? "bad" : "warn";

export const EVIDENCE_KINDS = ["document", "claim", "adjustment"];
export const isEvidence = (kind: string) => EVIDENCE_KINDS.includes(kind);

export const KIND_LABEL: Record<string, string> = {
  document: "Document",
  claim: "Claim",
  adjustment: "Adjustment",
  check: "Check",
  metric: "Metric",
  decision: "Decision",
};

export const SCENARIOS = [
  { key: "A", title: "Scenario A", blurb: "Legitimate difference, fully reconciled" },
  { key: "B", title: "Scenario B", blurb: "Hard contradiction: tax 80 vs P&L 60" },
  { key: "C", title: "Scenario C", blurb: "Material unexplained gap" },
] as const;
