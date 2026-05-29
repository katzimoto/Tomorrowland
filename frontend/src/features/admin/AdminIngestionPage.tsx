import { useState, useCallback, Fragment } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Activity,
} from "lucide-react";
import {
  adminApi,
  type IngestionStatusJob,
  type DocumentTraceResponse,
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

function TracePanel({
  documentId,
  onClose,
}: {
  documentId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { show: showToast } = useToast();

  const {
    data: trace,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["document-trace", documentId],
    queryFn: () => adminApi.getDocumentTrace(documentId),
    retry: false,
  });

  const requeueMutation = useMutation({
    mutationFn: () => adminApi.requeueDocument(documentId),
    onSuccess: (result) => {
      if (result.requeued === 0) {
        showToast("warning", "No dead-letter jobs found for this document.");
      } else {
        showToast("success", `Requeued ${result.requeued} job(s) for processing.`);
      }
      qc.invalidateQueries({ queryKey: ["document-trace", documentId] });
      qc.invalidateQueries({ queryKey: ["ingestion-status"] });
    },
    onError: (err: Error) => {
      showToast("error", err.message);
    },
  });

  if (isLoading) {
    return <div className={styles.detailLoading}>Loading trace…</div>;
  }

  if (error) {
    const is404 =
      error instanceof Error && error.message.includes("404");
    return (
      <div className={styles.detailError}>
        {is404
          ? "No pipeline trace found for this document."
          : error instanceof Error
            ? error.message
            : "Failed to load document trace."}
      </div>
    );
  }

  if (!trace || trace.jobs.length === 0) {
    return (
      <div className={styles.detailEmpty}>No pipeline jobs recorded for this document.</div>
    );
  }

  return (
    <div>
      <h4 className={styles.detailHeader}>
        Pipeline trace — {trace.document_title ?? documentId}
      </h4>
      <div className={styles.detailMeta}>
        {trace.source_name && <span>Source: {trace.source_name}</span>}
        <span>Jobs: {trace.jobs.length}</span>
      </div>

      <div className={styles.detailJobs}>
        {trace.jobs.map((job) => (
          <div key={job.id} className={styles.traceRow}>
            <div className={styles.traceRowMeta}>
              <span className={styles.traceRowTitle}>
                {job.job_type}
              </span>
              <span className={styles.traceRowSub}>
                Status: {job.status}
                {job.stage ? ` | Stage: ${job.stage}` : ""}
                {` | Attempts: ${job.attempts}/${job.max_attempts}`}
                {` | ${formatDateTime(job.created_at)}`}
              </span>
              {job.last_error && (
                <span className={styles.traceError}>
                  Error: {job.last_error}
                </span>
              )}
            </div>
            <div className={styles.traceActions}>
              <Badge variant={statusBadgeVariant(job.status)}>
                {job.status}
              </Badge>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: "var(--space-3)" }}>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => requeueMutation.mutate()}
          loading={requeueMutation.isPending}
        >
          <RefreshCw size={13} />
          Requeue document
        </Button>
      </div>
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
                        {job.document_title ?? job.document_id.slice(0, 8) + "…"}
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
                      <tr key={`${job.id}-trace`} className={styles.detailRow}>
                        <td colSpan={8}>
                          <div className={styles.detailPanel}>
                            <TracePanel
                              documentId={job.document_id}
                              onClose={() => setExpandedDocId(null)}
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
