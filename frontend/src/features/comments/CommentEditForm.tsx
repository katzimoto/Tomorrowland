import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateComment } from "@/api/comments";
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
    mutationFn: () => updateComment(docId, commentId, body.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["comments", docId] });
      onSaved();
    },
  });

  return (
    <form className={styles.form} onSubmit={(event) => { event.preventDefault(); if (body.trim()) mutation.mutate(); }}>
      <label className={styles.sr} htmlFor={`edit-${commentId}`}>Edit comment</label>
      <textarea id={`edit-${commentId}`} className={styles.textarea} value={body} onChange={(event) => setBody(event.target.value)} />
      <div className={styles.actions}>
        <Button type="submit" size="sm" disabled={!body.trim()} loading={mutation.isPending}>Save</Button>
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
