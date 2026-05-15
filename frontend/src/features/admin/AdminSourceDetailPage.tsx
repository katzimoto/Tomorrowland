import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import styles from "./AdminSourcesPage.module.css";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function AdminSourceDetailPage() {
  const navigate = useNavigate();
  const { sourceId } = useParams({ from: "/app/admin/sources/$sourceId" });

  const { data: source, isLoading, isError } = useQuery({
    queryKey: ["admin-source", sourceId],
    queryFn: () => adminApi.getSource(sourceId!),
    enabled: !!sourceId,
  });

  if (isLoading) {
    return (
      <div className={styles.page}>
        <SkeletonRow count={8} />
      </div>
    );
  }

  if (isError || !source) {
    return (
      <div className={styles.page}>
        <EmptyState title="Source not found" body="The source could not be loaded." />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>{source.name}</h1>
        <Badge variant={source.enabled ? "success" : "neutral"}>
          {source.enabled ? "Enabled" : "Disabled"}
        </Badge>
      </div>

      <div className={styles.section}>
        <h2>Configuration</h2>
        <dl className={styles.dl}>
          <dt>Type</dt>
          <dd>{source.type}</dd>
          <dt>Path</dt>
          <dd>{source.path || "—"}</dd>
          <dt>Language</dt>
          <dd>{source.source_language || "—"}</dd>
          {Object.entries(source.config).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd><code>{String(value)}</code></dd>
            </div>
          ))}
        </dl>
      </div>

      <div className={styles.section}>
        <h2>Sync Status</h2>
        {source.last_sync_status ? (
          <dl className={styles.dl}>
            <dt>Status</dt>
            <dd>
              <Badge variant={source.last_sync_status === "failed" ? "danger" : "success"}>
                {source.last_sync_status}
              </Badge>
            </dd>
            <dt>Indexed</dt>
            <dd>{source.last_sync_indexed ?? 0}</dd>
            <dt>Skipped</dt>
            <dd>{source.last_sync_skipped ?? 0}</dd>
            <dt>Failed</dt>
            <dd>{source.last_sync_failed ?? 0}</dd>
            {source.last_sync_at && <dt>Last run</dt>}
            {source.last_sync_at && <dd>{formatDateTime(source.last_sync_at)}</dd>}
            {source.last_sync_error && <dt>Error</dt>}
            {source.last_sync_error && <dd className={styles.error}>{source.last_sync_error}</dd>}
          </dl>
        ) : (
          <p className={styles.mutedMeta}>Never synced</p>
        )}
      </div>

      <div className={styles.section}>
        <h2>Validation</h2>
        {source.last_validation_status ? (
          <dl className={styles.dl}>
            <dt>Status</dt>
            <dd>
              <Badge
                variant={
                  source.last_validation_status === "ok" ? "success" : "danger"
                }
              >
                {source.last_validation_status}
              </Badge>
            </dd>
            {source.last_validated_at && <dt>Last checked</dt>}
            {source.last_validated_at && <dd>{formatDateTime(source.last_validated_at)}</dd>}
            {source.last_validation_error && <dt>Error</dt>}
            {source.last_validation_error && (
              <dd className={styles.error}>{source.last_validation_error}</dd>
            )}
          </dl>
        ) : (
          <p className={styles.mutedMeta}>Not yet validated</p>
        )}
      </div>

      <div className={styles.section}>
        <h2>Permissions</h2>
        {source.groups.length > 0 ? (
          <ul className={styles.groupList}>
            {source.groups.map((g) => (
              <li key={g.id}>
                <Badge variant="neutral">{g.name}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.mutedMeta}>No groups granted</p>
        )}
      </div>
    </div>
  );
}
