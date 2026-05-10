import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import type { SubscriptionWrite } from "@/api/subscriptions";
import { Button } from "@/components/primitives/Button";
import styles from "./SubscriptionsPage.module.css";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  query: z.string().trim().min(1, "Query is required"),
  similarity_threshold: z.coerce.number().min(0.5).max(1),
  enabled: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

interface SubscriptionFormProps {
  defaultValues: SubscriptionWrite;
  onSubmit: (values: SubscriptionWrite) => void;
  onCancel?: () => void;
  loading?: boolean;
}

export function SubscriptionForm({ defaultValues, onSubmit, onCancel, loading = false }: SubscriptionFormProps) {
  const { register, handleSubmit, formState: { errors }, control } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues,
  });
  const threshold = useWatch({ control, name: "similarity_threshold" });

  return (
    <form className={styles.formFields} onSubmit={handleSubmit((values) => onSubmit(values))}>
      <label className={styles.field}>Name<input {...register("name")} /></label>
      {errors.name && <span role="alert" className={styles.muted}>{errors.name.message}</span>}
      <label className={styles.field}>Query<input {...register("query")} /></label>
      {errors.query && <span role="alert" className={styles.muted}>{errors.query.message}</span>}
      <label className={styles.sliderLabel}>Threshold: {Math.round(Number(threshold) * 100)}%<input className={styles.slider} type="range" min={0.5} max={1} step={0.01} {...register("similarity_threshold")} /></label>
      <label className={styles.checkRow}><input type="checkbox" {...register("enabled")} /> Enabled</label>
      <div className={styles.formActions}><Button type="submit" loading={loading}>Save subscription</Button>{onCancel && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}</div>
    </form>
  );
}
