import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import type { SubscriptionWrite } from "@/api/subscriptions";
import { Button } from "@/components/primitives/Button";
import { useT } from "@/i18n/index";
import styles from "./SubscriptionsPage.module.css";

type FormValues = {
  name: string;
  query: string;
  similarity_threshold: number;
  enabled: boolean;
};

interface SubscriptionFormProps {
  defaultValues: SubscriptionWrite;
  onSubmit: (values: SubscriptionWrite) => void;
  onCancel?: () => void;
  loading?: boolean;
}

export function SubscriptionForm({ defaultValues, onSubmit, onCancel, loading = false }: SubscriptionFormProps) {
  const t = useT();

  const schema = z.object({
    name: z.string().trim().min(1, t.subscriptions.nameRequired),
    query: z.string().trim().min(1, t.subscriptions.queryRequired),
    similarity_threshold: z.coerce.number().min(0.5).max(1),
    enabled: z.boolean(),
  });

  const { register, handleSubmit, formState: { errors }, control } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues,
  });
  const threshold = useWatch({ control, name: "similarity_threshold" });

  return (
    <form className={styles.formFields} onSubmit={handleSubmit((values) => onSubmit(values))}>
      <label className={styles.field}>{t.subscriptions.nameLabel}<input {...register("name")} /></label>
      {errors.name && <span role="alert" className={styles.muted}>{errors.name.message}</span>}
      <label className={styles.field}>{t.subscriptions.queryLabel}<input {...register("query")} /></label>
      {errors.query && <span role="alert" className={styles.muted}>{errors.query.message}</span>}
      <label className={styles.sliderLabel}>{t.subscriptions.thresholdLabel(Math.round(Number(threshold) * 100))}<input className={styles.slider} type="range" min={0.5} max={1} step={0.01} {...register("similarity_threshold")} /></label>
      <label className={styles.checkRow}><input type="checkbox" {...register("enabled")} /> {t.subscriptions.enabledLabel}</label>
      <div className={styles.formActions}><Button type="submit" loading={loading}>{t.subscriptions.saveBtn}</Button>{onCancel && <Button type="button" variant="secondary" onClick={onCancel}>{t.subscriptions.cancelBtn}</Button>}</div>
    </form>
  );
}
