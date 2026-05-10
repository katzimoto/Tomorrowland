import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { ApiError } from "@/api/client";
import { listComments } from "@/api/comments";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { CommentComposer } from "./CommentComposer";
import { CommentItem } from "./CommentItem";
import styles from "./Comments.module.css";

interface CommentListProps {
  docId: string;
  enabled?: boolean;
}

export function CommentList({ docId, enabled = true }: CommentListProps) {
  const t = useT();
  const userQuery = useQuery({ queryKey: ["current-user"], queryFn: getCurrentUser, enabled });
  const commentsQuery = useQuery({ queryKey: ["comments", docId], queryFn: () => listComments(docId), enabled, staleTime: 2 * 60_000 });

  if (!enabled) return null;
  if (commentsQuery.isLoading) return <SkeletonRow compact count={3} />;
  if (commentsQuery.error instanceof ApiError && commentsQuery.error.status === 403) {
    return <EmptyState title={t.comments.unavailableTitle} body={t.comments.unavailableBody} />;
  }
  if (commentsQuery.isError) return <EmptyState title={t.comments.failedTitle} body={t.comments.failedBody} />;

  const comments = commentsQuery.data ?? [];
  return (
    <section className={styles.panel} aria-label={t.comments.ariaLabel}>
      {comments.length === 0 ? <EmptyState title={t.comments.emptyTitle} body={t.comments.emptyBody} /> : (
        <ul className={styles.list}>
          {comments.map((comment) => <li key={comment.id}><CommentItem docId={docId} comment={comment} currentUser={userQuery.data} /></li>)}
        </ul>
      )}
      <CommentComposer docId={docId} />
    </section>
  );
}
