import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { ApiError } from "@/api/client";
import { listComments } from "@/api/comments";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { CommentComposer } from "./CommentComposer";
import { CommentItem } from "./CommentItem";
import styles from "./Comments.module.css";

interface CommentListProps {
  docId: string;
  enabled?: boolean;
}

export function CommentList({ docId, enabled = true }: CommentListProps) {
  const userQuery = useQuery({ queryKey: ["current-user"], queryFn: getCurrentUser, enabled });
  const commentsQuery = useQuery({ queryKey: ["comments", docId], queryFn: () => listComments(docId), enabled });

  if (!enabled) return null;
  if (commentsQuery.isLoading) return <SkeletonRow compact count={3} />;
  if (commentsQuery.error instanceof ApiError && commentsQuery.error.status === 403) {
    return <EmptyState title="Comments unavailable" body="You do not have access to this document's collaboration notes." />;
  }
  if (commentsQuery.isError) return <EmptyState title="Could not load comments" body="Try again later." />;

  const comments = commentsQuery.data ?? [];
  return (
    <section className={styles.panel} aria-label="Comments">
      {comments.length === 0 ? <EmptyState title="No comments yet" body="Start the conversation for readers with access." /> : (
        <ul className={styles.list}>
          {comments.map((comment) => <li key={comment.id}><CommentItem docId={docId} comment={comment} currentUser={userQuery.data} /></li>)}
        </ul>
      )}
      <CommentComposer docId={docId} />
    </section>
  );
}
