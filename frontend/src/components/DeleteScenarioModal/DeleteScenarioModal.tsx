import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, Trash2, X } from "lucide-react";

type Props = {
  scenarioName: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
};

export function DeleteScenarioModal({ scenarioName, onClose, onConfirm }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !deleting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, deleting]);

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete scenario.");
      setDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && !deleting && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-scenario-title"
        className="modal-in flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-lg bg-panel shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="delete-scenario-title" className="text-lg font-bold text-ink">
              Delete scenario?
            </h2>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            disabled={deleting}
            aria-label="Close dialog"
            className="rounded p-1 text-ink-2 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4 p-5">
          {error && (
            <div role="alert" className="flex items-start gap-1.5 rounded-md border border-bad/30 bg-bad-soft p-3 text-xs text-bad">
              <AlertCircle size={14} className="shrink-0 mt-0.5" aria-hidden />
              <span>{error}</span>
            </div>
          )}

          <p className="text-sm text-ink-2">
            This permanently deletes <strong className="font-semibold text-ink">{scenarioName}</strong> and all its uploaded files. This can't be undone.
          </p>

          <div className="mt-2 flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={deleting}
              className="rounded-md border border-line px-3.5 py-1.5 text-sm font-medium text-ink-2 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleDelete()}
              disabled={deleting}
              className="flex items-center gap-1.5 rounded-md bg-bad px-4 py-1.5 text-sm font-semibold text-white hover:bg-bad/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {deleting ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <Trash2 size={14} aria-hidden />}
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
