import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { listEvidencePacks } from "@/api/evidencePacks";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import styles from "./EvidencePacksPage.module.css";

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function EvidencePacksPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["evidence-packs"],
    queryFn: listEvidencePacks,
    staleTime: 2 * 60_000,
  });
  const packs = data?.items ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Evidence packs</h1>
      </header>

      {isLoading && <SkeletonRow count={4} />}
      {isError && (
        <EmptyState title="Could not load evidence packs" body="Please try again." />
      )}
      {!isLoading && !isError && packs.length === 0 && (
        <EmptyState
          title="No evidence packs yet"
          body="Save citations or passages from chat, search, or the Evidence Inspector to start a pack."
        />
      )}
      {packs.length > 0 && (
        <ul className={styles.list}>
          {packs.map((pack) => (
            <li key={pack.id}>
              <Link
                to="/evidence/$packId"
                params={{ packId: pack.id }}
                className={styles.row}
              >
                <div className={styles.rowMain}>
                  <span className={styles.rowTitle}>{pack.title}</span>
                  {pack.description && (
                    <span className={styles.rowDesc}>{pack.description}</span>
                  )}
                </div>
                <div className={styles.rowMeta}>
                  <Badge variant="neutral">{pack.created_from}</Badge>
                  <span className={styles.rowDate}>{formatDate(pack.updated_at)}</span>
                  <ChevronRight size={16} aria-hidden />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
