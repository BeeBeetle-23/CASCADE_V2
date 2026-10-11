import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import { TONE_CLASSES, statusLabel, toneOf } from "../lib/status";

const ICON = { good: CheckCircle2, warn: AlertTriangle, bad: XCircle, muted: CircleDashed } as const;

/** Status is always shown as icon + text, never color alone. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = toneOf(status);
  const Icon = ICON[tone];
  const c = TONE_CLASSES[tone];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${c.bg} ${c.text}`}>
      <Icon size={12} aria-hidden />
      {label ?? statusLabel(status)}
    </span>
  );
}
