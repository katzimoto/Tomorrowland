import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateComment, type Comment } from "@/api/comments";
import { Button } from "@/components/primitives/Button";
import styles from "./Comments.module.css";

interface CommentEditFormProps {
  docId: string;
  commentId: string;
  initialBody: string;
  onCancel: () => void;
  onSaved: () => void;
}

export function CommentEditForm({ docId, commentId, initialBody, onCancel, onSaved }: CommentEditFormProps) {
  const [body, setBody] = useState(initialBody);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (draft: string) => updateComment(docId, commentId, draft),
    onMutate: async (draft) => {
      await queryClient.cancelQueries({ queryKey: ["comments", docId] });
      const previous = queryClient.getQueryData<Comment[]>(["comments", docId]);
      queryClient.setQueryData<Comment[]>(["comments", docId], (current = []) =>
        current.map((comment) => comment.id === commentId
          ? { ...comment, body: draft, updated_at: new Date().toISOString() }
          : comment),
      );
      onSaved();
      return { previous };
    },
    onError: (_error, _draft, context) => {
      if (context?.previous) queryClient.setQueryData(["comments", docId], context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["comments", docId] }),
  });

  return (
    <form className={styles.form} onSubmit={(event) => { event.preventDefault(); if (body.trim()) mutation.mutate(body.trim()); }}>
      <label className={styles.sr} htmlFor={`edit-${commentId}`}>Edit comment</label>
      <textarea id={`edit-${commentId}`} className={styles.textarea} value={body} onChange={(event) => setBody(event.target.value)} />
      <div className={styles.actions}>
        <Button type="submit" size="sm" disabled={!body.trim()} loading={mutation.isPending}>Save</Button>
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
