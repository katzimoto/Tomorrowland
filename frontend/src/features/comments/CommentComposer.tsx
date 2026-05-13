import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createComment, type Comment } from "@/api/comments";
import { Button } from "@/components/primitives/Button";
import styles from "./Comments.module.css";

interface CommentComposerProps {
  docId: string;
}

export function CommentComposer({ docId }: CommentComposerProps) {
  const [body, setBody] = useState("");
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (draft: string) => createComment(docId, draft),
    onMutate: async (draft) => {
      await queryClient.cancelQueries({ queryKey: ["comments", docId] });
      const previous = queryClient.getQueryData<Comment[]>(["comments", docId]);
      const optimistic: Comment = {
        id: `optimistic-${Date.now()}`,
        doc_id: docId,
        author_id: "current-user",
        author_name: "Reader",
        body: draft,
        created_at: new Date().toISOString(),
        updated_at: null,
      };
      queryClient.setQueryData<Comment[]>(["comments", docId], (current = []) => [...current, optimistic]);
      setBody("");
      return { previous };
    },
    onError: (_error, _draft, context) => {
      if (context?.previous) queryClient.setQueryData(["comments", docId], context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["comments", docId] }),
  });

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        if (body.trim()) mutation.mutate(body.trim());
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
