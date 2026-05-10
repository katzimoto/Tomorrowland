import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createComment } from "@/api/comments";
import { Button } from "@/components/primitives/Button";
import styles from "./Comments.module.css";

interface CommentComposerProps {
  docId: string;
}

export function CommentComposer({ docId }: CommentComposerProps) {
  const [body, setBody] = useState("");
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => createComment(docId, body.trim()),
    onSuccess: () => {
      setBody("");
      void queryClient.invalidateQueries({ queryKey: ["comments", docId] });
    },
  });

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        if (body.trim()) mutation.mutate();
      }}
    >
      <label htmlFor={`comment-${docId}`}>Add a comment</label>
      <textarea
        id={`comment-${docId}`}
        className={styles.textarea}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="Share context with readers…"
      />
      <div className={styles.actions}>
        <Button type="submit" disabled={!body.trim()} loading={mutation.isPending}>Post comment</Button>
        {mutation.isError && <span role="alert" className={styles.muted}>Could not post comment.</span>}
      </div>
    </form>
  );
}
