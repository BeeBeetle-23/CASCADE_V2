import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { api } from "../../api/client";
import type { ApplicationSummary } from "../../types";

type Props = {
  onClose: () => void;
  onSuccess: (app: ApplicationSummary) => void;
};

export function NewScenarioModal({ onClose, onSuccess }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [companyName, setCompanyName] = useState("");
  const [requestedAmount, setRequestedAmount] = useState("");
  const [reportingPeriod, setReportingPeriod] = useState("FY2025-26");

  const [nameError, setNameError] = useState<string | null>(null);
  const [amountError, setAmountError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    let hasError = false;

    const trimmedName = companyName.trim();
    if (!trimmedName) {
      setNameError("Company name is required.");
      hasError = true;
    } else {
      setNameError(null);
    }

    const numAmount = parseFloat(requestedAmount.trim());
    if (!requestedAmount.trim() || isNaN(numAmount) || numAmount <= 0) {
      setAmountError("Requested amount must be greater than 0.");
      hasError = true;
    } else {
      setAmountError(null);
    }

    if (hasError) return;

    setSubmitting(true);
    setApiError(null);
    try {
      const app = await api.createApplication({
        company_name: trimmedName,
        requested_amount: numAmount,
        currency: "INR",
        reporting_period: reportingPeriod.trim() || "FY2025-26",
      });
      onSuccess(app);
      onClose();
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create scenario.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-scenario-title"
        className="modal-in flex max-h-full w-full max-w-lg flex-col overflow-hidden rounded-lg bg-panel shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="new-scenario-title" className="text-lg font-bold">
              New scenario
            </h2>
            <p className="text-sm text-ink-2">
              Create a custom credit scenario and upload your own evidence.
            </p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded p-1 text-ink-2 hover:bg-paper"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-5">
          {apiError && (
            <div role="alert" className="rounded-md border border-bad/30 bg-bad-soft p-3 text-xs text-bad">
              {apiError}
            </div>
          )}

          <div>
            <label htmlFor="company-name" className="block text-sm font-semibold text-ink">
              Company name <span className="text-bad">*</span>
            </label>
            <input
              id="company-name"
              type="text"
              value={companyName}
              onChange={(e) => {
                setCompanyName(e.target.value);
                if (nameError) setNameError(null);
              }}
              disabled={submitting}
              placeholder="e.g. Alpha Tech LLC"
              className="mt-1.5 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-ink"
            />
            <p className="mt-1 text-xs text-ink-2">
              Use the exact name printed on your PDFs. Documents that don't mention it get a warning.
            </p>
            {nameError && <p className="mt-1 text-xs text-bad">{nameError}</p>}
          </div>

          <div>
            <label htmlFor="requested-amount" className="block text-sm font-semibold text-ink">
              Requested amount (lakh INR) <span className="text-bad">*</span>
            </label>
            <input
              id="requested-amount"
              type="number"
              min="0.01"
              step="any"
              value={requestedAmount}
              onChange={(e) => {
                setRequestedAmount(e.target.value);
                if (amountError) setAmountError(null);
              }}
              disabled={submitting}
              placeholder="e.g. 250"
              className="mt-1.5 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-ink"
            />
            {amountError && <p className="mt-1 text-xs text-bad">{amountError}</p>}
          </div>

          <div>
            <label htmlFor="reporting-period" className="block text-sm font-semibold text-ink">
              Reporting period
            </label>
            <input
              id="reporting-period"
              type="text"
              value={reportingPeriod}
              onChange={(e) => setReportingPeriod(e.target.value)}
              disabled={submitting}
              placeholder="FY2025-26"
              className="mt-1.5 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-ink"
            />
          </div>

          <div className="mt-2 flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-md border border-line px-3.5 py-1.5 text-sm font-medium text-ink-2 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-1.5 rounded-md bg-ink px-4 py-1.5 text-sm font-semibold text-white hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting && <Loader2 size={14} className="animate-spin" aria-hidden />}
              Create scenario
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
