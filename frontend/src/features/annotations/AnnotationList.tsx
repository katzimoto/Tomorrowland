import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { ApiError } from "@/api/client";
import { listAnnotations } from "@/api/annotations";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { AnnotationEditor } from "./AnnotationEditor";
import { AnnotationItem } from "./AnnotationItem";
import styles from "./Annotations.module.css";

interface AnnotationListProps {
  docId: string;
  enabled?: boolean;
}

export function AnnotationList({ docId, enabled = true }: AnnotationListProps) {
  const t = useT();
  const userQuery = useQuery({ queryKey: ["current-user"], queryFn: getCurrentUser, enabled });
  const annotationsQuery = useQuery({ queryKey: ["annotations", docId], queryFn: () => listAnnotations(docId), enabled, staleTime: 2 * 60_000 });

  if (!enabled) return null;
  if (annotationsQuery.isLoading) return <SkeletonRow compact count={3} />;
  if (annotationsQuery.error instanceof ApiError && annotationsQuery.error.status === 403) {
    return <EmptyState title={t.annotations.unavailableTitle} body={t.annotations.unavailableBody} />;
  }
  if (annotationsQuery.isError) return <EmptyState title={t.annotations.failedTitle} body={t.annotations.failedBody} />;

  const annotations = annotationsQuery.data ?? [];
  return (
    <section className={styles.panel} aria-label={t.annotations.ariaLabel}>
      {annotations.length === 0 ? <EmptyState title={t.annotations.emptyTitle} body={t.annotations.emptyBody} /> : (
        <ul className={styles.list}>{annotations.map((annotation) => <li key={annotation.id}><AnnotationItem docId={docId} annotation={annotation} currentUser={userQuery.data} /></li>)}</ul>
      )}
      <AnnotationEditor docId={docId} />
    </section>
  );
}
