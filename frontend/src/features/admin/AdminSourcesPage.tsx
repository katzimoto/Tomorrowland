import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, RefreshCw, ServerIcon } from "lucide-react";
import { adminApi, type ConnectorType, type SyncResult } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { Dialog } from "@/components/primitives/Dialog";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import styles from "./AdminSourcesPage.module.css";

type FormValues = {
  name: string;
  type: string;
  source_language: string;
  config: Record<string, string>;
};

export function AdminSourcesPage() {
  const t = useT();
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [syncResults, setSyncResults] = useState<
    Record<string, SyncResult | string>
  >({});

  const { data: connectorTypes = [], isLoading: typesLoading } = useQuery({
    queryKey: ["connector-types"],
    queryFn: adminApi.connectorTypes,
  });

  const { data: sources = [], isLoading: sourcesLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: adminApi.listSources,
  });

  const createMutation = useMutation({
    mutationFn: adminApi.createSource,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      setDialogOpen(false);
      reset();
    },
  });

  const schema = z.object({
    name: z.string().min(1, t.admin.colName),
    type: z.string().min(1, t.admin.typeLabel),
    source_language: z.string().min(1),
    config: z.record(z.string()),
  });

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      type: connectorTypes[0]?.type ?? "folder",
      source_language: "en",
      config: {},
    },
  });

  const selectedType = useWatch({ control, name: "type" });
  const currentSpec: ConnectorType | undefined = connectorTypes.find(
    (c) => c.type === selectedType,
  );

  async function onSubmit(values: FormValues) {
    const payload = {
      name: values.name,
      type: values.type,
      source_language: values.source_language,
      enabled: true,
      config: values.config,
      // For folder sources, also set top-level path for backward compat
      ...(values.type === "folder" && values.config.path
        ? { path: values.config.path }
        : {}),
    };
    await createMutation.mutateAsync(payload);
  }

  async function handleSync(sourceId: string) {
    setSyncResults((r) => ({ ...r, [sourceId]: "syncing" }));
    try {
      const result = await measurePerformance("sourceSync.action", () =>
        adminApi.syncSource(sourceId),
      );
      setSyncResults((r) => ({ ...r, [sourceId]: result }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      setSyncResults((r) => ({ ...r, [sourceId]: msg }));
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t.admin.title}</h1>
        <Button onClick={() => setDialogOpen(true)} disabled={typesLoading}>
          <Plus size={16} />
          {t.admin.addSource}
        </Button>
      </div>

      {sourcesLoading ? (
        <SkeletonRow count={3} className={styles.skeletons} />
      ) : sources.length === 0 ? (
        <EmptyState
          icon={<ServerIcon size={32} />}
          title={t.admin.noSourcesTitle}
          body={t.admin.noSourcesBody}
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t.admin.colName}</th>
                <th>{t.admin.colType}</th>
                <th>{t.admin.colLang}</th>
                <th>{t.admin.colEnabled}</th>
                <th>{t.admin.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => {
                const result = syncResults[src.id];
                return (
                  <tr key={src.id}>
                    <td className={styles.nameCell}>{src.name}</td>
                    <td>
                      <Badge variant="neutral">{src.type}</Badge>
                    </td>
                    <td>{src.source_language ?? "—"}</td>
                    <td>{src.enabled ? "✓" : "—"}</td>
                    <td>
                      <div className={styles.actions}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleSync(src.id)}
                          loading={result === "syncing"}
                        >
                          <RefreshCw size={13} />
                          {t.admin.syncBtn}
                        </Button>
                      </div>
                      {result && result !== "syncing" && (
                        <p
                          className={`${styles.syncResult} ${
                            typeof result === "object" && result.failed > 0
                              ? styles.syncError
                              : typeof result === "string"
                                ? styles.syncError
                                : styles.syncOk
                          }`}
                        >
                          {typeof result === "object"
                            ? t.admin.syncResult(
                                result.indexed,
                                result.skipped,
                                result.failed,
                              )
                            : result}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          reset();
        }}
        title={t.admin.dialogTitle}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className={styles.form}
          noValidate
        >
          <TextInput
            label={t.admin.nameLabel}
            placeholder={t.admin.namePlaceholder}
            error={errors.name?.message}
            {...register("name")}
          />

          <div className={styles.field}>
            <label className={styles.label} htmlFor="src-type">
              {t.admin.typeLabel}
            </label>
            <select
              id="src-type"
              className={styles.select}
              {...register("type")}
            >
              {connectorTypes.map((c) => (
                <option key={c.type} value={c.type}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {currentSpec && currentSpec.fields.length > 0 && (
            <div className={styles.configSection}>
              <p className={styles.configLabel}>
                {t.admin.settingsLabel(currentSpec.label)}
              </p>
              {currentSpec.fields.map((f) => (
                <TextInput
                  key={f.key}
                  label={f.label + (f.required ? "" : " (optional)")}
                  type={f.sensitive ? "password" : "text"}
                  placeholder={f.placeholder}
                  autoComplete={f.sensitive ? "new-password" : undefined}
                  {...register(`config.${f.key}`)}
                />
              ))}
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.label} htmlFor="src-lang">
              {t.admin.langLabel}
            </label>
            <select
              id="src-lang"
              className={styles.select}
              {...register("source_language")}
            >
              <option value="en">English (en)</option>
              <option value="fr">French (fr)</option>
              <option value="de">German (de)</option>
              <option value="es">Spanish (es)</option>
              <option value="ar">Arabic (ar)</option>
              <option value="zh">Chinese (zh)</option>
              <option value="auto">Auto-detect</option>
            </select>
          </div>

          {createMutation.error && (
            <p className={styles.formError} role="alert">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : t.admin.createError}
            </p>
          )}

          <div className={styles.dialogActions}>
            <Button type="submit" loading={isSubmitting}>
              {t.admin.saveBtn}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setDialogOpen(false);
                reset();
              }}
            >
              {t.admin.cancelBtn}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
