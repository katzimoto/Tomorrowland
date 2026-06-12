import { useState, useCallback, Fragment } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  RotateCw,
  SkipForward,
  Activity,
  AlertTriangle,
  XCircle,
  Clock,
  Minus,
} from "lucide-react";
import {
  adminApi,
  type IngestionStatusJob,
  type TimelineStage,
} from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminIngestionPage.module.css";

const PAGE_LIMIT = 25;

const STATUS_OPTIONS = ["", "pending", "running", "completed", "failed", "cancelled"];

function statusBadgeVariant(status: string) {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "danger";
    case "running":
      return "warning";
    default:
      return "neutral";
  }
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function truncateError(msg: string | null, max = 80) {
  if (!msg) return null;
  return msg.length > max ? msg.slice(0, max) + "…" : msg;
}

function getStageIcon(status: TimelineStage["status"]) {
  switch (status) {
    case "completed":
      return <CheckCircle size={16} className={styles.stageIconCompleted} />;
    case "failed":
      return <XCircle size={16} className={styles.stageIconFailed} />;
    case "running":
      return <RefreshCw size={16} className={styles.stageIconRunning} />;
    case "pending":
      return <Clock size={16} className={styles.stageIconPending} />;
    case "skipped":
      return <Minus size={16} className={styles.stageIconSkipped} />;
  }
}

function formatDuration(ms: number | null) {
  if (ms == null) return null;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60_000);
  const secs = Math.round((ms % 60_000) / 1000);
  return `${mins}m ${secs}s`;
}

const RETRY_ACTIONS: Array<{
  label: string;
  action: "retry" | "reprocess" | "reocr" | "retranslate" | "reembed";
  relevantStages: string[];
}> = [
  { label: "Retry failed stage", action: "retry", relevantStages: [] },
  { label: "Reprocess", action: "reprocess", relevantStages: ["parsed", "extract", "ocr", "chunk"] },
  { label: "Re-OCR", action: "reocr", relevantStages: ["ocr"] },
  { label: "Retranslate", action: "retranslate", relevantStages: ["translate", "translated"] },
  { label: "Re-embed", action: "reembed", relevantStages: ["embedded", "indexed"] },
];

function getFailedStages(stages: TimelineStage[]): string[] {
  return stages.filter((s) => s.status === "failed").map((s) => s.stage);
}

function isRetryActionRelevant(
  action: typeof RETRY_ACTIONS[number],
  failedStages: string[],
): boolean {
  // "Retry failed stage" is always relevant if there are failures
  if (action.action === "retry") return true;
  // Other actions are relevant if any failed stage matches
  return action.relevantStages.some((s) => failedStages.includes(s));
}

function TimelinePanel({
  documentId,
}: {
  documentId: string;
}) {
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const {
    data: timeline,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["document-timeline", documentId],
    queryFn: () => adminApi.getDocumentTimeline(documentId),
    retry: false,
  });

  const buildRetryMutation = (action: string) => {
    const actionFns: Record<string, (id: string) => Promise<{ requeued: number; action: string }>> = {
      retry: adminApi.retryDocument,
      reprocess: adminApi.reprocessDocument,
      reocr: adminApi.reocrDocument,
      retranslate: adminApi.retranslateDocument,
      reembed: adminApi.reembedDocument,
    };
    return useMutation({
      mutationFn: () => actionFns[action](documentId),
      onSuccess: (result) => {
        setConfirmAction(null);
        if (result.requeued === 0) {
          showToast("info", "No jobs needed requeueing — the document may already be processed.");
        } else {
          showToast("success", `${action}: requeued ${result.requeued} job(s).`);
        }
        qc.invalidateQueries({ queryKey: ["document-timeline", documentId] });
        qc.invalidateQueries({ queryKey: ["ingestion-status"] });
      },
      onError: (err: Error) => {
        setConfirmAction(null);
        showToast("error", err.message);
      },
    });
  };

  // We need the full set of mutations — use individual ones for loading states
  const retryMutation = buildRetryMutation("retry");
  const reprocessMutation = buildRetryMutation("reprocess");
  const reocrMutation = buildRetryMutation("reocr");
  const retranslateMutation = buildRetryMutation("retranslate");
  const reembedMutation = buildRetryMutation("reembed");

  const mutationMap: Record<string, typeof retryMutation> = {
    retry: retryMutation,
    reprocess: reprocessMutation,
    reocr: reocrMutation,
    retranslate: retranslateMutation,
    reembed: reembedMutation,
  };

  if (isLoading) {
    return <div className={styles.detailLoading}>Loading timeline…</div>;
  }

  if (error) {
    const is404 =
      error instanceof Error && error.message.includes("404");
    return (
      <div className={styles.detailError}>
        {is404
          ? "No pipeline timeline found for this document."
          : error instanceof Error
            ? error.message
            : "Failed to load document timeline."}
      </div>
    );
  }

  if (!timeline || timeline.stages.length === 0) {
    return (
      <div className={styles.detailEmpty}>No pipeline stages recorded for this document.</div>
    );
  }

  const hasFailures = timeline.stages.some((s) => s.status === "failed");

  return (
    <div>
      <div className={styles.timelineHeader}>
        <h4 className={styles.detailHeader}>
          Processing timeline — {timeline.document_title ?? documentId}
        </h4>
        {timeline.source_name && (
          <span className={styles.timelineSource}>
            Source: {timeline.source_name}
          </span>
        )}
      </div>

      {/* Stage timeline */}
      <div className={styles.timelineTrack}>
        {timeline.stages.map((stage, idx) => (
          <div key={`${stage.stage}-${idx}`} className={styles.timelineNode}>
            <div className={styles.timelineConnector}>
              <div className={styles.timelineDot}>
                {getStageIcon(stage.status)}
              </div>
              {idx < timeline.stages.length - 1 && (
                <div
                  className={`${styles.timelineLine} ${
                    stage.status === "completed"
                      ? styles.timelineLineFilled
                      : styles.timelineLineEmpty
                  }`}
                />
              )}
            </div>
            <div className={styles.timelineStage}>
              <div className={styles.timelineStageHeader}>
                <span className={styles.timelineStageName}>
                  {stage.stage.charAt(0).toUpperCase() + stage.stage.slice(1)}
                </span>
                <Badge
                  variant={
                    stage.status === "completed"
                      ? "success"
                      : stage.status === "failed"
                        ? "danger"
                        : stage.status === "running"
                          ? "warning"
                          : "neutral"
                  }
                >
                  {stage.status}
                </Badge>
              </div>
              <div className={styles.timelineStageMeta}>
                {stage.at && (
                  <span>{formatDateTime(stage.at)}</span>
                )}
                {stage.duration_ms != null && (
                  <span className={styles.timelineDuration}>
                    {formatDuration(stage.duration_ms)}
                  </span>
                )}
              </div>
              {stage.error && (
                <div className={styles.timelineError}>
                  <AlertTriangle size={13} />
                  {stage.error}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Retry actions — context-sensitive based on failed stages */}
      {hasFailures && (
        <div className={styles.retrySection}>
          <div className={styles.retryLabel}>Retry actions</div>
          <div className={styles.retryActions}>
            {RETRY_ACTIONS.filter((ra) =>
              isRetryActionRelevant(ra, getFailedStages(timeline.stages)),
            ).map(({ label, action }) => {
              const mutation = mutationMap[action];
              return (
                <div key={action}>
                  {confirmAction === action ? (
                    <div className={styles.confirmRow}>
                      <span className={styles.confirmText}>
                        {label} for this document?
                      </span>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => mutation.mutate()}
                        loading={mutation.isPending}
                      >
                        Confirm
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setConfirmAction(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setConfirmAction(action)}
                    >
                      {action === "retry" && <RefreshCw size={13} />}
                      {action === "reprocess" && <RotateCw size={13} />}
                      {action === "reocr" && <SkipForward size={13} />}
                      {action === "retranslate" && <SkipForward size={13} />}
                      {action === "reembed" && <RotateCw size={13} />}
                      {label}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminIngestionPage() {
  const navigate = useNavigate();

  const [statusFilter, setStatusFilter] = useState("");
  const [sourceIdFilter, setSourceIdFilter] = useState("");
  const [sinceFilter, setSinceFilter] = useState("");
  const [offset, setOffset] = useState(0);

  const filterParams = {
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(sourceIdFilter ? { source_id: sourceIdFilter } : {}),
    ...(sinceFilter ? { since: sinceFilter } : {}),
    limit: PAGE_LIMIT,
    offset,
  };

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["ingestion-status", filterParams],
    queryFn: () => adminApi.getIngestionStatus(filterParams),
    refetchInterval: 10_000,
  });

  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);

  const toggleExpand = useCallback((docId: string) => {
    setExpandedDocId((prev) => (prev === docId ? null : docId));
  }, []);

  const handleClearFilters = useCallback(() => {
    setStatusFilter("");
    setSourceIdFilter("");
    setSinceFilter("");
    setOffset(0);
  }, []);

  const hasFilters = statusFilter || sourceIdFilter || sinceFilter;

  const jobs = data?.jobs ?? [];
  const total = data?.total ?? 0;
  const summary = data?.summary ?? {};
  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT));
  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Admin
        </Button>
        <h1 className={styles.title}>Ingestion Pipeline</h1>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          <RefreshCw size={14} />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className={styles.summaryRow}>
        <div className={`${styles.summaryCard} ${styles.summaryCardPending}`}>
          <span className={styles.summaryLabel}>Pending</span>
          <span className={styles.summaryValue}>{summary.pending ?? 0}</span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardRunning}`}>
          <span className={styles.summaryLabel}>Running</span>
          <span className={styles.summaryValue}>{summary.running ?? 0}</span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardCompleted}`}>
          <span className={styles.summaryLabel}>Completed</span>
          <span className={styles.summaryValue}>{summary.completed ?? 0}</span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardFailed}`}>
          <span className={styles.summaryLabel}>Failed</span>
          <span className={styles.summaryValue}>{summary.failed ?? 0}</span>
        </div>
      </div>

      {/* Filter bar */}
      <div className={styles.filterBar}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel} htmlFor="filter-status">
            Status
          </label>
          <select
            id="filter-status"
            className={styles.filterSelect}
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setOffset(0);
            }}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel} htmlFor="filter-source">
            Source ID
          </label>
          <input
            id="filter-source"
            className={styles.filterInput}
            type="text"
            placeholder="Filter by source ID"
            value={sourceIdFilter}
            onChange={(e) => {
              setSourceIdFilter(e.target.value);
              setOffset(0);
            }}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel} htmlFor="filter-since">
            Since
          </label>
          <input
            id="filter-since"
            className={styles.filterInput}
            type="date"
            value={sinceFilter}
            onChange={(e) => {
              setSinceFilter(e.target.value);
              setOffset(0);
            }}
          />
        </div>

        {hasFilters && (
          <Button variant="secondary" size="sm" onClick={handleClearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {/* Error state */}
      {isError && (
        <div className={styles.errorBox} role="alert">
          {error instanceof Error ? error.message : "Failed to load ingestion status."}
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <SkeletonRow count={5} className={styles.skeletons} />
      )}

      {/* Empty state */}
      {!isLoading && !isError && jobs.length === 0 && (
        <EmptyState
          icon={<Activity size={32} />}
          title="No pipeline jobs"
          body={
            hasFilters
              ? "No jobs match the current filters. Try clearing them."
              : "No ingestion pipeline jobs have been recorded yet."
          }
        />
      )}

      {/* Table */}
      {!isLoading && !isError && jobs.length > 0 && (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.expandCell}></th>
                  <th>Document</th>
                  <th>Source</th>
                  <th>Job type</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Error</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job: IngestionStatusJob) => (
                  <Fragment key={job.id}>
                    <tr>
                      <td className={styles.expandCell}>
                        <button
                          type="button"
                          className={styles.expandBtn}
                          onClick={() => toggleExpand(job.document_id)}
                          aria-label={
                            expandedDocId === job.document_id
                              ? "Collapse trace"
                              : "Expand trace"
                          }
                        >
                          {expandedDocId === job.document_id ? (
                            <ChevronDown size={14} />
                          ) : (
                            <ChevronRight size={14} />
                          )}
                        </button>
                      </td>
                      <td className={styles.nameCell}>
                        <a
                          className={styles.docLink}
                          href={`/doc/${job.document_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={
                            job.document_title
                              ? `Open ${job.document_title}`
                              : "Open document"
                          }
                        >
                          {job.document_title ?? job.document_id.slice(0, 8) + "…"}
                          <ExternalLink size={11} />
                        </a>
                      </td>
                      <td>{job.source_name ?? job.source_id.slice(0, 8) + "…"}</td>
                      <td>{job.job_type}</td>
                      <td>
                        <Badge variant={statusBadgeVariant(job.status)}>
                          {job.status}
                        </Badge>
                      </td>
                      <td>
                        {job.attempts}/{job.max_attempts}
                      </td>
                      <td className={styles.errorCell} title={job.last_error ?? undefined}>
                        {truncateError(job.last_error) ?? "—"}
                      </td>
                      <td className={styles.dateCell}>
                        {formatDateTime(job.updated_at)}
                      </td>
                    </tr>
                    {expandedDocId === job.document_id && (
                      <tr key={`${job.id}-timeline`} className={styles.detailRow}>
                        <td colSpan={8}>
                          <div className={styles.detailPanel}>
                            <TimelinePanel
                              documentId={job.document_id}
                            />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className={styles.pagination}>
            <Button
              variant="secondary"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_LIMIT))}
            >
              Previous
            </Button>
            <span className={styles.pageInfo}>
              Page {currentPage} of {totalPages} ({total} total)
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={offset + PAGE_LIMIT >= total}
              onClick={() => setOffset((o) => o + PAGE_LIMIT)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
