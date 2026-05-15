import { useCallback, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, PlugZap, Plus, RefreshCw, ServerIcon } from "lucide-react";
import { adminApi, type ConnectorType, type Source, type SyncResult } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { Dialog } from "@/components/primitives/Dialog";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminSourcesPage.module.css";

type FormValues = {
  name: string;
  type: string;
  source_language: string;
  config: Record<string, string>;
};

export function AdminSourcesPage() {
  const t = useT();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [syncResults, setSyncResults] = useState<Record<string, SyncResult | string>>({});
  const [testResults, setTestResults] = useState<Record<string, string>>({});

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

  const handleSync = useCallback(async (sourceId: string) => {
    const src = sources.find((s) => s.id === sourceId);
    const name = src?.name ?? sourceId;
    showToast("info", t.admin.syncStarted(name));
    setSyncResults((r) => ({ ...r, [sourceId]: "syncing" }));
    try {
      const result = await measurePerformance("sourceSync.action", () =>
        adminApi.syncSource(sourceId),
      );
      setSyncResults((r) => ({ ...r, [sourceId]: result }));
      qc.invalidateQueries({ queryKey: ["sources"] });
      if (result.failed > 0) {
        showToast("error", t.admin.syncPartialFailure(result.failed));
      } else {
        showToast("success", t.admin.syncCompleted(result.indexed, result.skipped, result.failed));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      setSyncResults((r) => ({ ...r, [sourceId]: msg }));
      showToast("error", t.admin.syncFailed);
    }
  }, [sources, showToast, t]);


  async function handleTestConnection(sourceId: string) {
    setTestResults((r) => ({ ...r, [sourceId]: "testing" }));
    try {
      const result = await adminApi.testSource(sourceId);
      if (result.status === "ok") {
        setTestResults((r) => ({ ...r, [sourceId]: t.admin.testConnectionOk }));
      } else {
        const errorMsg = result.error || t.admin.testConnectionError;
        setTestResults((r) => ({ ...r, [sourceId]: errorMsg }));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : t.admin.testConnectionError;
      setTestResults((r) => ({ ...r, [sourceId]: msg }));
    }
  }

  function renderSyncSummary(src: Source, result: SyncResult | string | undefined) {
    if (result === "syncing") return null;
    const liveResult = typeof result === "object" ? result : undefined;
    const errorResult = typeof result === "string" ? result : undefined;
    const indexed = liveResult?.indexed ?? src.last_sync_indexed;
    const skipped = liveResult?.skipped ?? src.last_sync_skipped;
    const failed = liveResult?.failed ?? src.last_sync_failed;
    const status = liveResult?.status ?? src.last_sync_status;
    const error = errorResult ?? (status === "failed" ? src.last_sync_error : null);

    if (indexed === null && skipped === null && failed === null && !error) {
      return <span className={styles.mutedMeta}>{t.admin.neverSynced}</span>;
    }

    return (
      <div className={styles.syncSummary}>
        {status && (
          <Badge variant={status === "failed" ? "danger" : "success"}>
            {status === "failed" ? t.admin.syncStatusFailed : t.admin.syncStatusSuccess}
          </Badge>
        )}
        <span>{t.admin.syncResult(indexed ?? 0, skipped ?? 0, failed ?? 0)}</span>
        {src.last_sync_at && <span>{t.admin.lastSynced(formatDateTime(src.last_sync_at))}</span>}
        {error && <span className={styles.syncError}>{error}</span>}
      </div>
    );
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
                <th>{t.admin.colLastSync}</th>
                <th>{t.admin.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => {
                const result = syncResults[src.id];
                const testResult = testResults[src.id];
                return (
                  <tr key={src.id}>
                    <td className={styles.nameCell}>
                      <a
                        href={`/admin/sources/${src.id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          void navigate({ to: "/admin/sources/$sourceId", params: { sourceId: src.id } });
                        }}
                      >
                        {src.name}
                      </a>
                    </td>
                    <td>
                      <Badge variant="neutral">{src.type}</Badge>
                    </td>
                    <td>{src.source_language ?? "—"}</td>
                    <td>{src.enabled ? "✓" : "—"}</td>
                    <td>{renderSyncSummary(src, result)}</td>
                    <td>
                      <div className={styles.actions}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleTestConnection(src.id)}
                          loading={testResult === "testing"}
                        >
                          <PlugZap size={13} />
                          {t.admin.testConnectionBtn}
                        </Button>
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
                      {testResult && testResult !== "testing" && (
                        <p
                          className={`${styles.syncResult} ${
                            testResult === t.admin.testConnectionOk ? styles.syncOk : styles.syncError
                          }`}
                        >
                          <CheckCircle2 size={13} />
                          {testResult}
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
