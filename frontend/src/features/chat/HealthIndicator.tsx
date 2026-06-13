import { useState } from "react";
import { AlertTriangle, CheckCircle, XCircle, HelpCircle, ChevronDown, ChevronRight } from "lucide-react";
import { useT } from "@/i18n/index";
import type { EvidenceHealthSummary } from "@/api/admin";
import styles from "./HealthIndicator.module.css";

interface HealthIndicatorProps {
  summary: EvidenceHealthSummary | null | undefined;
  loading?: boolean;
}

const ICON_MAP = {
  healthy: CheckCircle,
  degraded: AlertTriangle,
  failed: XCircle,
  unknown: HelpCircle,
} as const;

const STATUS_LABEL_KEYS = {
  healthy: "evidenceSourceHealthHealthy" as const,
  degraded: "evidenceSourceHealthDegraded" as const,
  failed: "evidenceSourceHealthFailed" as const,
  unknown: "evidenceSourceHealthUnknown" as const,
} as const;

const VARIANT_CLASS = {
  healthy: styles.variantHealthy,
  degraded: styles.variantDegraded,
  failed: styles.variantFailed,
  unknown: styles.variantUnknown,
} as const;

export function HealthIndicator({ summary, loading }: HealthIndicatorProps) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className={styles.row}>
        <span className={styles.label}>{t.chat.evidenceSourceHealth}</span>
        <span className={styles.loading}>…</span>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className={styles.row}>
        <span className={styles.label}>{t.chat.evidenceSourceHealth}</span>
        <span className={styles.value}>{t.chat.evidenceSourceHealthNoData}</span>
      </div>
    );
  }

  const status = summary.status;
  const Icon = ICON_MAP[status];
  const variantClass = VARIANT_CLASS[status];
  const labelKey = STATUS_LABEL_KEYS[status];
  const badgeLabel = t.chat[labelKey];
  const hasIssues = (summary.issues?.length ?? 0) > 0;

  return (
    <div className={styles.wrapper}>
      <div className={styles.row}>
        <span className={styles.label}>{t.chat.evidenceSourceHealth}</span>
        <span className={`${styles.badge} ${variantClass}`}>
          <Icon size={14} />
          {badgeLabel}
        </span>
        {hasIssues && (
          <button
            className={styles.expandBtn}
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Collapse issues" : "Expand issues"}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        )}
      </div>
      {expanded && hasIssues && (
        <div className={styles.issueList}>
          {summary.issues!.map((issue) => (
            <div key={issue.code} className={styles.issueRow}>
              <span className={`${styles.issueSeverity} ${severityClass(issue.severity)}`} />
              <span className={styles.issueLabel}>{issue.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function severityClass(severity: string | undefined | null): string {
  switch (severity) {
    case "critical":
      return styles.severityCritical;
    case "warning":
      return styles.severityWarning;
    default:
      return styles.severityInfo;
  }
}
