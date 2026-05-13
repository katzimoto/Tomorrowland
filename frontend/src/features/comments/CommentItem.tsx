import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteComment, type Comment } from "@/api/comments";
import type { CurrentUser } from "@/api/auth";
import { Button } from "@/components/primitives/Button";
import { CommentEditForm } from "./CommentEditForm";
import styles from "./Comments.module.css";

const COLLAPSE_AT = 420;

interface CommentItemProps {
  docId: string;
  comment: Comment;
  currentUser?: CurrentUser;
}

function authorName(comment: Comment): string {
  return comment.author?.display_name ?? comment.author_name ?? "Reader";
}

export function CommentItem({ docId, comment, currentUser }: CommentItemProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const canManage = currentUser?.is_admin || currentUser?.user_id === comment.author_id;
  const longComment = comment.body.length > COLLAPSE_AT;
  const body = !expanded && longComment ? `${comment.body.slice(0, COLLAPSE_AT)}…` : comment.body;
  const remove = useMutation({
    mutationFn: () => deleteComment(docId, comment.id),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["comments", docId] });
      const previous = queryClient.getQueryData<Comment[]>(["comments", docId]);
      queryClient.setQueryData<Comment[]>(["comments", docId], (current = []) =>
        current.filter((item) => item.id !== comment.id),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["comments", docId], context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["comments", docId] }),
  });

  return (
    <article className={styles.item} aria-label={`Comment by ${authorName(comment)}`}>
      <div className={styles.meta}>
        <strong>{authorName(comment)}</strong>
        <time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleString()}</time>
        {comment.updated_at && <span>Edited <time dateTime={comment.updated_at}>{new Date(comment.updated_at).toLocaleString()}</time></span>}
      </div>
      {editing ? (
        <CommentEditForm docId={docId} commentId={comment.id} initialBody={comment.body} onCancel={() => setEditing(false)} onSaved={() => setEditing(false)} />
      ) : (
        <>
          <p className={`${styles.body} ${expanded ? styles.expanded : ""}`}>{body}</p>
          {longComment && <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((value) => !value)}>{expanded ? "Show less" : "Show more"}</Button>}
          {canManage && (
            <div className={styles.actions}>
              <Button type="button" variant="secondary" size="sm" onClick={() => setEditing(true)}>Edit</Button>
              <Button type="button" variant="danger" size="sm" onClick={() => remove.mutate()} loading={remove.isPending}>Delete</Button>
            </div>
          )}
        </>
      )}
    </article>
  );
}
