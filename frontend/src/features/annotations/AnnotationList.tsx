import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { ApiError } from "@/api/client";
import { listAnnotations } from "@/api/annotations";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { AnnotationEditor } from "./AnnotationEditor";
import { AnnotationItem } from "./AnnotationItem";
import styles from "./Annotations.module.css";

interface AnnotationListProps {
  docId: string;
  enabled?: boolean;
}

export function AnnotationList({ docId, enabled = true }: AnnotationListProps) {
  const userQuery = useQuery({ queryKey: ["current-user"], queryFn: getCurrentUser, enabled });
  const annotationsQuery = useQuery({ queryKey: ["annotations", docId], queryFn: () => listAnnotations(docId), enabled });

  if (!enabled) return null;
  if (annotationsQuery.isLoading) return <SkeletonRow compact count={3} />;
  if (annotationsQuery.error instanceof ApiError && annotationsQuery.error.status === 403) {
    return <EmptyState title="Annotations unavailable" body="You do not have access to this document's annotations." />;
  }
  if (annotationsQuery.isError) return <EmptyState title="Could not load annotations" body="Try again later." />;

  const annotations = annotationsQuery.data ?? [];
  return (
    <section className={styles.panel} aria-label="Annotations">
      {annotations.length === 0 ? <EmptyState title="No annotations yet" body="Add private notes or share evidence with readers." /> : (
        <ul className={styles.list}>{annotations.map((annotation) => <li key={annotation.id}><AnnotationItem docId={docId} annotation={annotation} currentUser={userQuery.data} /></li>)}</ul>
      )}
      <AnnotationEditor docId={docId} />
    </section>
  );
}
