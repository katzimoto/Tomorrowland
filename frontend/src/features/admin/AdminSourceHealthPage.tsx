import { useState, useMemo, useCallback, Fragment } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueries, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Activity,
  ChevronDown,
  ChevronRight,
  Play,
  ExternalLink,
} from "lucide-react";
import {
  adminApi,
  type SourceHealthResponse,
} from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import { en } from "@/i18n/locales/en";
import styles from "./AdminSourceHealthPage.module.css";

const t = en.admin.sourceHealth;

// --- Helpers ---

type Severity = "healthy" | "degraded" | "failed" | "no-check";

interface HealthStatus {
  label: string;
  variant: "success" | "warning" | "danger" | "neutral";
  severity: Severity;
}

function getHealthStatus(qa: SourceHealthResponse | undefined): HealthStatus {
  if (!qa || !qa.checked_at) {
    return { label: t.noCheck, variant: "neutral", severity: "no-check" };
  }
  if (qa.failed_documents > 0) {
    return { label: t.failed, variant: "danger", severity: "failed" };
  }
  if (qa.issues && qa.issues.length > 0) {
    return { label: t.degraded, variant: "warning", severity: "degraded" };
  }
  return { label: t.healthy, variant: "success", severity: "healthy" };
}

function mapAction(issue: string): string {
  const lower = issue.toLowerCase();
  if (lower.includes("missing content")) return t.actionContent;
  if (lower.includes("missing metadata") || lower.includes("empty metadata"))
    return t.actionMetadata;
  if (lower.includes("no title") || lower.includes("missing title"))
    return t.actionTitle;
  if (lower.includes("may need ocr") || lower.includes("empty text may need"))
    return t.actionOcr;
  if (lower.includes("index lag") || lower.includes("pending for over"))
    return t.actionLag;
  return t.actionReextract;
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

// --- Component ---

export function AdminSourceHealthPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const toggleExpand = useCallback((id: string) => {
    setExpandedRowId((prev) => (prev === id ? null : id));
  }, []);

  // Fetch all sources
  const {
    data: sources,
    isLoading: isSourcesLoading,
    isError: isSourcesError,
  } = useQuery({
    queryKey: ["sources"],
    queryFn: adminApi.listSources,
  });

  // Fetch QA for each source
  const qaQueries = useQueries({
    queries: (sources ?? []).map((source) => ({
      queryKey: ["source-qa", source.id],
      queryFn: () => adminApi.getSourceHealth(source.id),
      enabled: !!source.id,
      retry: false,
    })),
  });

  // Aggregate summary
  const summary = useMemo(() => {
    return qaQueries.reduce(
      (acc, query) => {
        if (query.data) {
          acc.total += query.data.total_documents || 0;
          acc.indexed += query.data.indexed_documents || 0;
          acc.pending += query.data.pending_documents || 0;
          acc.failed += query.data.failed_documents || 0;
        }
        return acc;
      },
      { total: 0, indexed: 0, pending: 0, failed: 0 },
    );
  }, [qaQueries]);

  // "Run QA" mutation — calls the GET endpoint to trigger a fresh check
  const runQaMutation = useMutation({
    mutationFn: (sourceId: string) => adminApi.getSourceHealth(sourceId),
    onSuccess: (data) => {
      qc.setQueryData(["source-qa", data.source_id], data);
      showToast("success", "QA check completed.");
    },
    onError: () => {
      showToast("error", "Failed to run QA check.");
    },
  });

  const isLoading =
    isSourcesLoading ||
    (sources !== undefined && sources.length > 0 && qaQueries.some((q) => q.isLoading));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate({ to: "/admin" })}
        >
          <ArrowLeft size={16} />
          Admin
        </Button>
        <h1 className={styles.title}>{t.title}</h1>
        <div className={styles.headerSpacer} />
      </div>

      {/* Summary cards */}
      <div className={styles.summaryRow}>
        <div className={`${styles.summaryCard} ${styles.summaryCardTotal}`}>
          <span className={styles.summaryLabel}>{t.summaryTotal}</span>
          <span className={styles.summaryValue}>
            {summary.total.toLocaleString()}
          </span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardIndexed}`}>
          <span className={styles.summaryLabel}>{t.summaryIndexed}</span>
          <span className={styles.summaryValue}>
            {summary.indexed.toLocaleString()}
          </span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardPending}`}>
          <span className={styles.summaryLabel}>{t.summaryPending}</span>
          <span className={styles.summaryValue}>
            {summary.pending.toLocaleString()}
          </span>
        </div>
        <div className={`${styles.summaryCard} ${styles.summaryCardFailed}`}>
          <span className={styles.summaryLabel}>{t.summaryFailed}</span>
          <span className={styles.summaryValue}>
            {summary.failed.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Error state */}
      {isSourcesError && (
        <div className={styles.errorBox} role="alert">
          {t.error}
        </div>
      )}

      {/* Loading state */}
      {isLoading && <SkeletonRow count={5} className={styles.skeletons} />}

      {/* Empty state (no sources) */}
      {!isLoading && !isSourcesError && (!sources || sources.length === 0) && (
        <EmptyState
          icon={<Activity size={32} />}
          title={t.noSources}
          body={t.noSourcesBody}
        />
      )}

      {/* Table */}
      {!isLoading && sources && sources.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.expandCell} />
                <th>{t.sourceName}</th>
                <th>{t.healthStatus}</th>
                <th>{t.docCounts}</th>
                <th>{t.lastCheck}</th>
                <th className={styles.actionsCell}>{t.runQa}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source, index) => {
                const qa = qaQueries[index]?.data;
                const health = getHealthStatus(qa);
                const isExpanded = expandedRowId === source.id;

                return (
                  <Fragment key={source.id}>
                    <tr>
                      <td className={styles.expandCell}>
                        <button
                          type="button"
                          className={styles.expandBtn}
                          onClick={() => toggleExpand(source.id)}
                          aria-label={
                            isExpanded ? "Collapse details" : "Expand details"
                          }
                        >
                          {isExpanded ? (
                            <ChevronDown size={14} />
                          ) : (
                            <ChevronRight size={14} />
                          )}
                        </button>
                      </td>
                      <td className={styles.nameCell}>
                        <a
                          href={`/admin/sources/${source.id}`}
                          className={styles.sourceLink}
                        >
                          {source.name}
                          <ExternalLink size={11} />
                        </a>
                      </td>
                      <td>
                        <Badge variant={health.variant}>
                          {health.label}
                        </Badge>
                      </td>
                      <td className={styles.countsCell}>
                        {qa
                          ? `${qa.indexed_documents} / ${qa.pending_documents} / ${qa.failed_documents}`
                          : "—"}
                      </td>
                      <td className={styles.dateCell}>
                        {formatDateTime(qa?.checked_at ?? null)}
                      </td>
                      <td className={styles.actionsCell}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => runQaMutation.mutate(source.id)}
                          loading={
                            runQaMutation.isPending &&
                            runQaMutation.variables === source.id
                          }
                        >
                          <Play size={13} />
                          {t.runQa}
                        </Button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className={styles.detailRow}>
                        <td colSpan={6}>
                          <div className={styles.detailPanel}>
                            {!qa || !qa.checked_at ? (
                              <div className={styles.detailEmpty}>
                                {t.emptyStateBody}
                              </div>
                            ) : qa.issues.length === 0 ? (
                              <div className={styles.detailEmpty}>
                                No issues found.
                              </div>
                            ) : (
                              <div className={styles.issueList}>
                                {qa.issues.map((issue, i) => (
                                  <div key={i} className={styles.issueRow}>
                                    <div className={styles.issueText}>
                                      {issue}
                                    </div>
                                    <div className={styles.issueAction}>
                                      {mapAction(issue)}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
