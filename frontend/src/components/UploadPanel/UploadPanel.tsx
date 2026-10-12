import { useEffect, useRef, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, FileText, Loader2, Upload } from "lucide-react";
import { api, ApiError } from "../../api/client";
import type { ClaimOut, DocumentOut, DocumentType, UploadResult, UploadWarning } from "../../types";
import { TONE_CLASSES } from "../../lib/status";
import { StatusBadge } from "../StatusBadge";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

const CLAIM_LABELS: Record<string, string> = {
  bank_inflow_total: "Bank Inflow Total",
  internal_transfer: "Internal Transfer",
  loan_proceeds: "Loan Proceeds",
  refund_or_other_credit: "Refund / Other Credit",
  owner_equity_contribution: "Owner Equity Contribution",
  gross_revenue_tax: "Gross Revenue (Tax)",
  gross_revenue_pnl: "Gross Revenue (P&L)",
  cash_available_for_debt_service: "Cash Available for Debt Service",
  scheduled_debt_service: "Scheduled Debt Service",
  current_assets: "Current Assets",
  current_liabilities: "Current Liabilities",
};

function formatClaimType(type: string): string {
  return CLAIM_LABELS[type] ?? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function getWarningMessage(w: UploadWarning): string {
  switch (w.code) {
    case "llm_not_configured":
      return "LLM is not configured (API key missing); fell back to rule-based extraction.";
    case "llm_auth":
      return "LLM authentication failed; fell back to rule-based extraction.";
    case "llm_rate_limited":
      return "LLM rate limit reached; fell back to rule-based extraction.";
    case "llm_timeout":
      return "LLM request timed out; fell back to rule-based extraction.";
    case "llm_bad_response":
      return "LLM returned an invalid response; fell back to rule-based extraction.";
    case "entity_name_not_found":
      return w.message || "Company name was not found in this PDF.";
    case "type_conflict":
    case "duplicate_file":
      return w.message || `Document conflict: ${w.code}`;
    default:
      return w.message || `Warning: ${w.code}`;
  }
}

type ItemStatus = "queued" | "extracting" | "extracted" | "needs_type" | "accepted" | "error";

interface DocumentItem {
  id: string; // client temporary ID or doc ID
  filename: string;
  status: ItemStatus;
  statusMessage?: string;
  docId?: string;
  docType?: DocumentType;
  selectedType?: DocumentType;
  typeConfirmed?: boolean;
  extractionMode?: string | null;
  processingStatus?: string;
  claims?: ClaimOut[];
  warnings?: UploadWarning[];
  errorMessage?: string;
  isAccepting?: boolean;
  isConfirming?: boolean;
}

type Props = {
  appId: string;
  disabled?: boolean;
  onRefreshGraph: () => Promise<void>;
  onCascadeAccept: () => Promise<void>;
};

export function UploadPanel({ appId, disabled = false, onRefreshGraph, onCascadeAccept }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const processingRef = useRef(false);

  // Load existing documents for this custom application
  useEffect(() => {
    let cancelled = false;
    async function loadExistingDocs() {
      try {
        const [docs, claims] = await Promise.all([
          api.listDocuments(appId),
          api.getClaims(appId),
        ]);
        if (cancelled) return;

        const loadedItems: DocumentItem[] = docs.map((doc: DocumentOut) => {
          const currentVersion =
            doc.versions.find((v) => v.is_current) ?? doc.versions[doc.versions.length - 1];
          const procStatus = currentVersion?.processing_status;
          const verStatus = currentVersion?.verification_status;
          const isFailed = procStatus === "failed" || procStatus === "needs_ocr";
          const isVerified = verStatus === "verified";
          const needsType = doc.doc_type === "unknown";

          let status: ItemStatus = "extracted";
          if (isFailed) status = "error";
          else if (isVerified) status = "accepted";
          else if (needsType) status = "needs_type";

          const docClaims = claims.filter((c) => c.source_document_id === doc.id);
          const warnings = (currentVersion?.diagnostics ?? []).filter((d) => d.level !== "info");

          return {
            id: doc.id,
            filename: currentVersion?.original_filename || `${doc.doc_type}.pdf`,
            status,
            docId: doc.id,
            docType: doc.doc_type,
            selectedType: doc.doc_type,
            typeConfirmed: doc.type_confirmed,
            extractionMode: currentVersion?.extraction_mode,
            processingStatus: procStatus,
            claims: docClaims,
            warnings,
            errorMessage:
              procStatus === "needs_ocr"
                ? "Scanned PDF requiring OCR is not supported."
                : procStatus === "failed"
                ? "Document processing failed."
                : undefined,
          };
        });

        setItems(loadedItems);
      } catch {
        // App error handled by App.tsx
      }
    }

    void loadExistingDocs();
    return () => {
      cancelled = true;
    };
  }, [appId]);

  const validateFile = (file: File): string | null => {
    const isPdf =
      file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      return `"${file.name}" is not a PDF file. Only PDF files are supported.`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `"${file.name}" exceeds the 20 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`;
    }
    return null;
  };

  const processQueue = async (filesToProcess: { id: string; file: File }[]) => {
    if (processingRef.current) return;
    processingRef.current = true;

    for (const { id, file } of filesToProcess) {
      // Set status to extracting
      setItems((prev) =>
        prev.map((item) =>
          item.id === id
            ? { ...item, status: "extracting", statusMessage: "Extracting text and mapping claims…" }
            : item
        )
      );

      try {
        const result: UploadResult = await api.uploadDocument(appId, file, "analyst", true);

        // Immediately refresh graph and summary so nodes appear and empty state clears
        await onRefreshGraph();

        // Fetch claims to associate with this document
        const allClaims = await api.getClaims(appId);
        const docClaims = allClaims.filter((c) => c.source_document_id === result.document.id);

        const currentVersion =
          result.document.versions.find((v) => v.is_current) ??
          result.document.versions[result.document.versions.length - 1];
        const procStatus = currentVersion?.processing_status;
        const isFailed = procStatus === "failed" || procStatus === "needs_ocr";
        const needsType = result.needs_type_confirmation || result.document.doc_type === "unknown";

        let status: ItemStatus = "extracted";
        let errMsg: string | undefined = undefined;

        if (isFailed) {
          status = "error";
          errMsg =
            procStatus === "needs_ocr"
              ? "Scanned PDF requiring OCR is not supported."
              : "Document processing failed.";
        } else if (needsType) {
          status = "needs_type";
        }

        setItems((prev) =>
          prev.map((item) =>
            item.id === id
              ? {
                  ...item,
                  status,
                  docId: result.document.id,
                  docType: result.document.doc_type,
                  selectedType: result.document.doc_type,
                  typeConfirmed: result.document.type_confirmed,
                  extractionMode: result.extraction_mode,
                  processingStatus: procStatus,
                  claims: docClaims,
                  warnings: result.warnings ?? [],
                  errorMessage: errMsg,
                }
              : item
          )
        );
      } catch (err) {
        const errorMsg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
            ? err.message
            : "Upload failed.";

        setItems((prev) =>
          prev.map((item) =>
            item.id === id
              ? {
                  ...item,
                  status: "error",
                  errorMessage: errorMsg,
                }
              : item
          )
        );
      }
    }

    processingRef.current = false;
  };

  const handleFiles = (fileList: File[]) => {
    setValidationError(null);
    const validEntries: { id: string; file: File }[] = [];
    const errors: string[] = [];

    for (const file of fileList) {
      const err = validateFile(file);
      if (err) {
        errors.push(err);
      } else {
        const tempId = `temp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
        validEntries.push({ id: tempId, file });
      }
    }

    if (errors.length > 0) {
      setValidationError(errors.join(" "));
    }

    if (validEntries.length === 0) return;

    // Add valid files to items as queued
    const newItems: DocumentItem[] = validEntries.map(({ id, file }) => ({
      id,
      filename: file.name,
      status: "queued",
    }));

    setItems((prev) => [...prev, ...newItems]);
    void processQueue(validEntries);
  };

  const handleConfirmType = async (itemId: string) => {
    const item = items.find((i) => i.id === itemId);
    if (!item || !item.docId || !item.selectedType || item.selectedType === "unknown") return;

    setItems((prev) =>
      prev.map((i) => (i.id === itemId ? { ...i, isConfirming: true, errorMessage: undefined } : i))
    );

    try {
      const result = await api.confirmType(item.docId, item.selectedType, "analyst");
      await onRefreshGraph();

      const allClaims = await api.getClaims(appId);
      const docClaims = allClaims.filter((c) => c.source_document_id === result.document.id);

      const currentVersion =
        result.document.versions.find((v) => v.is_current) ??
        result.document.versions[result.document.versions.length - 1];

      setItems((prev) =>
        prev.map((i) =>
          i.id === itemId
            ? {
                ...i,
                status: "extracted",
                docType: result.document.doc_type,
                selectedType: result.document.doc_type,
                typeConfirmed: true,
                extractionMode: result.extraction_mode,
                processingStatus: currentVersion?.processing_status,
                claims: docClaims,
                warnings: result.warnings ?? [],
                isConfirming: false,
              }
            : i
        )
      );
    } catch (err) {
      const errorMsg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Failed to confirm type.";
      setItems((prev) =>
        prev.map((i) => (i.id === itemId ? { ...i, isConfirming: false, errorMessage: errorMsg } : i))
      );
    }
  };

  const handleAccept = async (itemId: string) => {
    const item = items.find((i) => i.id === itemId);
    if (!item || !item.docId) return;

    setItems((prev) =>
      prev.map((i) => (i.id === itemId ? { ...i, isAccepting: true, errorMessage: undefined } : i))
    );

    try {
      await api.acceptReview(item.docId, "analyst");
      // Cascade refresh in App
      await onCascadeAccept();

      // Refresh claims to reflect verified status
      const allClaims = await api.getClaims(appId);
      const docClaims = allClaims.filter((c) => c.source_document_id === item.docId);

      setItems((prev) =>
        prev.map((i) =>
          i.id === itemId
            ? {
                ...i,
                status: "accepted",
                claims: docClaims,
                isAccepting: false,
              }
            : i
        )
      );
    } catch (err) {
      const errorMsg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Failed to accept review.";
      setItems((prev) =>
        prev.map((i) => (i.id === itemId ? { ...i, isAccepting: false, errorMessage: errorMsg } : i))
      );
    }
  };

  return (
    <section aria-labelledby="docs-h" className="flex flex-col gap-3">
      <h2 id="docs-h" className="text-sm font-semibold text-ink-2">
        Documents
      </h2>

      {/* Dropzone */}
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload PDF documents"
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onClick={() => !disabled && fileInputRef.current?.click()}
        onDragEnter={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!disabled) setIsDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragging(false);
          if (disabled) return;
          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFiles(Array.from(e.dataTransfer.files));
          }
        }}
        className={`flex flex-col items-center justify-center rounded-md border-2 border-dashed p-4 text-center cursor-pointer transition-colors ${
          isDragging ? "border-trail bg-trail-soft" : "border-line bg-paper hover:bg-paper/80"
        } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
      >
        <Upload size={20} className="text-ink-2" aria-hidden />
        <p className="mt-1.5 text-xs font-medium text-ink">Drag & drop PDFs here or browse</p>
        <p className="text-[11px] text-ink-2">PDF up to 20 MB</p>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          disabled={disabled}
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFiles(Array.from(e.target.files));
              e.target.value = "";
            }
          }}
        />
      </div>

      {validationError && (
        <div role="alert" className="flex items-start gap-1.5 rounded-md bg-bad-soft p-2.5 text-xs text-bad">
          <AlertCircle size={14} className="shrink-0 mt-0.5" aria-hidden />
          <span>{validationError}</span>
        </div>
      )}

      {/* Document Items List */}
      {items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {items.map((item) => {
            const hasConflictOrError = item.status === "error";
            const isScannedOrFailed =
              item.processingStatus === "needs_ocr" || item.processingStatus === "failed";
            const canAccept =
              item.status !== "accepted" &&
              item.status !== "extracting" &&
              item.status !== "queued" &&
              !hasConflictOrError &&
              !isScannedOrFailed &&
              item.selectedType !== "unknown" &&
              (item.claims?.length ?? 0) > 0;

            const typeChanged =
              item.selectedType !== undefined &&
              item.docType !== undefined &&
              item.selectedType !== item.docType;
            const needsTypeConfirm =
              item.status === "needs_type" ||
              item.docType === "unknown" ||
              typeChanged ||
              (!item.typeConfirmed && item.selectedType !== undefined);

            return (
              <li key={item.id} className="rounded-md border border-line bg-panel p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <FileText size={15} className="shrink-0 text-ink-2" aria-hidden />
                    <span className="truncate text-xs font-semibold text-ink" title={item.filename}>
                      {item.filename}
                    </span>
                  </div>

                  {/* Status Badge */}
                  {item.status === "queued" && <StatusBadge status="unavailable" label="Queued" />}
                  {item.status === "extracting" && (
                    <span className="inline-flex items-center gap-1 rounded bg-trail-soft px-1.5 py-0.5 text-xs font-medium text-trail">
                      <Loader2 size={12} className="animate-spin" aria-hidden />
                      Extracting…
                    </span>
                  )}
                  {item.status === "extracted" && <StatusBadge status="amber" label="Extracted" />}
                  {item.status === "needs_type" && (
                    <StatusBadge status="amber" label="Needs type" />
                  )}
                  {item.status === "accepted" && <StatusBadge status="green" label="Accepted" />}
                  {item.status === "error" && <StatusBadge status="red" label="Failed" />}
                </div>

                {/* Status message while extracting */}
                {item.status === "extracting" && item.statusMessage && (
                  <p className="mt-2 text-xs text-ink-2 flex items-center gap-1.5">
                    <Loader2 size={12} className="animate-spin" aria-hidden />
                    {item.statusMessage}
                  </p>
                )}

                {/* Error message */}
                {item.errorMessage && (
                  <div className="mt-2 flex items-start gap-1.5 rounded bg-bad-soft p-2 text-xs text-bad">
                    <AlertCircle size={13} className="shrink-0 mt-0.5" aria-hidden />
                    <span>{item.errorMessage}</span>
                  </div>
                )}

                {/* Extracted Details */}
                {item.status !== "queued" && item.status !== "extracting" && (
                  <div className="mt-2.5 flex flex-col gap-2">
                    {/* Document Type Selector & Confirmation */}
                    <div className="flex flex-wrap items-center gap-2">
                      <label htmlFor={`type-${item.id}`} className="text-xs font-medium text-ink-2">
                        Type:
                      </label>
                      <select
                        id={`type-${item.id}`}
                        value={item.selectedType ?? "unknown"}
                        onChange={(e) => {
                          const val = e.target.value as DocumentType;
                          setItems((prev) =>
                            prev.map((i) => (i.id === item.id ? { ...i, selectedType: val } : i))
                          );
                        }}
                        disabled={disabled || item.status === "accepted" || item.isConfirming}
                        className="rounded border border-line bg-panel px-2 py-1 text-xs text-ink"
                      >
                        {item.docType === "unknown" && (
                          <option value="unknown" disabled>
                            Select document type…
                          </option>
                        )}
                        <option value="bank_statement">Bank Statement</option>
                        <option value="income_tax_return">Income Tax Return</option>
                        <option value="profit_and_loss">Profit &amp; Loss</option>
                      </select>

                      {needsTypeConfirm && item.status !== "accepted" && (
                        <button
                          type="button"
                          onClick={() => void handleConfirmType(item.id)}
                          disabled={
                            disabled ||
                            item.isConfirming ||
                            !item.selectedType ||
                            item.selectedType === "unknown"
                          }
                          className="flex items-center gap-1 rounded border border-line px-2 py-1 text-xs font-medium text-ink-2 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {item.isConfirming && <Loader2 size={11} className="animate-spin" aria-hidden />}
                          Confirm type
                        </button>
                      )}
                    </div>

                    {/* Badges row: mode and claims count */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {item.extractionMode === "llm_mapped" && (
                        <span className="inline-flex items-center gap-1 rounded bg-good-soft px-1.5 py-0.5 text-[11px] font-medium text-good">
                          AI-mapped
                        </span>
                      )}
                      {item.extractionMode === "deterministic_fallback" && (
                        <span className="inline-flex items-center gap-1 rounded bg-warn-soft px-1.5 py-0.5 text-[11px] font-medium text-warn">
                          Rule-based fallback
                        </span>
                      )}
                      {item.claims !== undefined && (
                        <span className="text-[11px] text-ink-2">
                          {item.claims.length} {item.claims.length === 1 ? "claim" : "claims"} created
                        </span>
                      )}
                    </div>

                    {/* Warnings */}
                    {item.warnings && item.warnings.length > 0 && (
                      <div className="flex flex-col gap-1">
                        {item.warnings.map((w, idx) => {
                          const isBad = w.level === "error" || w.level === "bad";
                          const c = isBad ? TONE_CLASSES.bad : TONE_CLASSES.warn;
                          return (
                            <div
                              key={idx}
                              className={`flex items-start gap-1.5 rounded p-2 text-xs ${c.bg} ${c.text}`}
                            >
                              <AlertTriangle size={13} className="shrink-0 mt-0.5" aria-hidden />
                              <span>{getWarningMessage(w)}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Claims list */}
                    {item.claims && item.claims.length > 0 && (
                      <div className="mt-1 flex flex-col gap-1.5">
                        <p className="text-[11px] font-semibold text-ink-2">Extracted claims</p>
                        <ul className="flex flex-col gap-1.5">
                          {item.claims.map((claim) => (
                            <li
                              key={claim.id}
                              className="rounded border border-line bg-paper p-2 text-xs"
                            >
                              <div className="flex items-center justify-between gap-1">
                                <span className="font-medium text-ink">
                                  {formatClaimType(claim.claim_type)}
                                </span>
                                <span className="font-semibold text-ink">
                                  {claim.value ?? "n/a"} {claim.unit}
                                </span>
                              </div>
                              <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-ink-2">
                                <span>{claim.page_number !== null ? `Page ${claim.page_number}` : "p. n/a"}</span>
                                <StatusBadge status={claim.verification_status} />
                              </div>
                              {claim.source_excerpt && (
                                <p
                                  className="mt-1 truncate text-[11px] text-ink-2"
                                  title={claim.source_excerpt}
                                >
                                  “{claim.source_excerpt}”
                                </p>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Accept button */}
                    {canAccept && (
                      <div className="mt-1 pt-1">
                        <button
                          type="button"
                          onClick={() => void handleAccept(item.id)}
                          disabled={disabled || item.isAccepting}
                          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-trail px-3 py-1.5 text-xs font-semibold text-white hover:bg-trail/90 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {item.isAccepting ? (
                            <Loader2 size={13} className="animate-spin" aria-hidden />
                          ) : (
                            <CheckCircle2 size={13} aria-hidden />
                          )}
                          Accept &amp; run cascade
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
