import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createAnnotation, updateAnnotation, type Annotation } from "@/api/annotations";
import { Button } from "@/components/primitives/Button";
import styles from "./Annotations.module.css";

const schema = z.object({
  body: z.string().trim().min(1, "Add annotation text"),
  shared: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

interface AnnotationEditorProps {
  docId: string;
  annotation?: Annotation;
  onDone?: () => void;
}

export function AnnotationEditor({ docId, annotation, onDone }: AnnotationEditorProps) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors }, reset } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { body: annotation?.body ?? "", shared: annotation?.shared ?? false },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => annotation
      ? updateAnnotation(annotation.id, { ...values, position: annotation.position ?? null })
      : createAnnotation(docId, { ...values, position: null }),
    onSuccess: () => {
      reset({ body: "", shared: false });
      void queryClient.invalidateQueries({ queryKey: ["annotations", docId] });
      onDone?.();
    },
  });

  return (
    <form className={styles.form} onSubmit={handleSubmit((values) => mutation.mutate(values))}>
      <label htmlFor={`annotation-body-${annotation?.id ?? "new"}`}>{annotation ? "Edit annotation" : "New annotation"}</label>
      <textarea id={`annotation-body-${annotation?.id ?? "new"}`} className={styles.textarea} {...register("body")} />
      {errors.body && <span role="alert" className={styles.muted}>{errors.body.message}</span>}
      <label className={styles.toggleRow}>
        <input className={styles.checkbox} type="checkbox" {...register("shared")} />
        Share with readers who can access this document
      </label>
      <div className={styles.actions}>
        <Button type="submit" loading={mutation.isPending}>{annotation ? "Save annotation" : "Create annotation"}</Button>
        {annotation && <Button type="button" variant="secondary" onClick={onDone}>Cancel</Button>}
      </div>
    </form>
  );
}
