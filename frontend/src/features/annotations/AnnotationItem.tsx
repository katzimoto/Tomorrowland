import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteAnnotation, type Annotation } from "@/api/annotations";
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

  return (
    <article className={styles.item} aria-label="Annotation">
      <div className={styles.meta}>
        <span>{annotation.author_name ?? "Reader"}</span>
        <PrivacyLabel shared={annotation.shared} />
      </div>
      <span className={styles.position}>{positionLabel(annotation.position)}</span>
      {editing ? <AnnotationEditor docId={docId} annotation={annotation} onDone={() => setEditing(false)} /> : (
        <>
          <p className={styles.body}>{annotation.body}</p>
          {canManage && <div className={styles.actions}><Button type="button" size="sm" variant="secondary" onClick={() => setEditing(true)}>Edit</Button><Button type="button" size="sm" variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete</Button></div>}
        </>
      )}
    </article>
  );
}
