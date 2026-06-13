import { api } from "./client";

/** Health status for a source/document. */
export type HealthStatus = "healthy" | "degraded" | "failed" | "unknown";

/** One detected issue within a health summary. */
export interface HealthIssue {
  code: string;
  label: string;
  severity: "info" | "warning" | "critical";
  safe_message: string;
}

/** Health summary payload returned by ``GET /sources/{id}/health-summary``. */
export interface EvidenceHealthSummary {
  status: HealthStatus;
  severity: "info" | "warning" | "critical" | null;
  issue_count: number;
  issues: HealthIssue[];
  latest_check_at: string | null;
}

/** Fetch a source health summary (any authenticated user). */
export function getSourceHealthSummary(
  sourceId: string,
): Promise<EvidenceHealthSummary> {
  return api.get<EvidenceHealthSummary>(
    `/sources/${sourceId}/health-summary`,
  );
}
