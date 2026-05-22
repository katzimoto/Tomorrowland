import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAnnotation,
  listReplies,
  createReply,
  deleteReply,
  type Annotation,
  type AnnotationReply,
} from "@/api/annotations";
import type { CurrentUser } from "@/api/auth";
import { Button } from "@/components/primitives/Button";
import { AnnotationEditor } from "./AnnotationEditor";
import { PrivacyLabel } from "./PrivacyLabel";
import styles from "./Annotations.module.css";

interface AnnotationItemProps {
  docId: string;
  annotation: Annotation;
  currentUser?: CurrentUser;
}

function positionLabel(position?: Record<string, unknown> | null): string {
  if (!position) return "Document note";
  if (typeof position.page === "number") return `Page ${position.page}`;
  if (typeof position.section === "string") return position.section;
  return "Document selection";
}

export function AnnotationItem({ docId, annotation, currentUser }: AnnotationItemProps) {
  const [editing, setEditing] = useState(false);
  const [showReplies, setShowReplies] = useState(false);
  const [replyBody, setReplyBody] = useState("");
  const queryClient = useQueryClient();
  const canManage = currentUser?.is_admin || currentUser?.user_id === annotation.author_id;

  const remove = useMutation({
    mutationFn: () => deleteAnnotation(annotation.id),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["annotations", docId] });
      const previous = queryClient.getQueryData<Annotation[]>(["annotations", docId]);
      queryClient.setQueryData<Annotation[]>(["annotations", docId], (current = []) =>
        current.filter((item) => item.id !== annotation.id),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["annotations", docId], context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["annotations", docId] }),
  });

  const replyCount = annotation.reply_count ?? 0;

  const { data: replies = [] } = useQuery({
    queryKey: ["annotation-replies", annotation.id],
    queryFn: () => listReplies(annotation.id),
    enabled: showReplies,
    staleTime: 30_000,
  });

  const addReply = useMutation({
    mutationFn: (body: string) => createReply(annotation.id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["annotation-replies", annotation.id] });
      void queryClient.invalidateQueries({ queryKey: ["annotations", docId] });
      setReplyBody("");
    },
  });

  const removeReply = useMutation({
    mutationFn: (replyId: string) => deleteReply(replyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["annotation-replies", annotation.id] });
      void queryClient.invalidateQueries({ queryKey: ["annotations", docId] });
    },
  });

  function handleAddReply() {
    const body = replyBody.trim();
    if (!body) return;
    addReply.mutate(body);
  }

  return (
    <article className={styles.item} aria-label="Annotation">
      <div className={styles.meta}>
        <span>{annotation.author_name ?? "Reader"}</span>
        <PrivacyLabel shared={annotation.shared} />
      </div>
      <span className={styles.position}>{positionLabel(annotation.position)}</span>
      {editing ? (
        <AnnotationEditor docId={docId} annotation={annotation} onDone={() => setEditing(false)} />
      ) : (
        <>
          <p className={styles.body}>{annotation.body}</p>
          <div className={styles.actions}>
            {canManage && (
              <>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="danger"
                  loading={remove.isPending}
                  onClick={() => remove.mutate()}
                >
                  Delete
                </Button>
              </>
            )}
            {replyCount > 0 || true ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setShowReplies(!showReplies)}
              >
                {showReplies ? "Hide replies" : `Replies${replyCount > 0 ? ` (${replyCount})` : ""}`}
              </Button>
            ) : null}
          </div>

          {showReplies && (
            <div className={styles.repliesSection}>
              {replies.map((r: AnnotationReply) => (
                <div key={r.id} className={styles.replyItem}>
                  <div className={styles.replyMeta}>
                    <span className={styles.replyAuthor}>
                      {r.author_name ?? "Reader"}
                    </span>
                    <span className={styles.replyDate}>
                      {new Date(r.created_at).toLocaleDateString()}
                    </span>
                    {r.can_modify && (
                      <button
                        className={styles.iconAction}
                        aria-label="Delete reply"
                        onClick={() => removeReply.mutate(r.id)}
                      >
                        ×
                      </button>
                    )}
                  </div>
                  <p className={styles.replyBody}>{r.body}</p>
                </div>
              ))}
              <div className={styles.addReply}>
                <input
                  className={styles.inlineInput}
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddReply();
                    }
                  }}
                  placeholder="Write a reply..."
                  aria-label="Reply text"
                />
                <Button
                  size="sm"
                  onClick={handleAddReply}
                  disabled={!replyBody.trim() || addReply.isPending}
                >
                  Reply
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </article>
  );
}
