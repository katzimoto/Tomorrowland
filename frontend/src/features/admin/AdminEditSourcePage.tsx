import { useState, useEffect } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Save } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminSourcesPage.module.css";

export function AdminEditSourcePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const { sourceId } = useParams({ from: "/app/admin/sources/$sourceId/edit" });

  const [name, setName] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [schedule, setSchedule] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [pathValue, setPathValue] = useState("");

  const { data: source, isLoading, isError } = useQuery({
    queryKey: ["admin-source", sourceId],
    queryFn: () => adminApi.getSource(sourceId!),
    enabled: !!sourceId,
  });

  const { data: connectorTypes = [] } = useQuery({
    queryKey: ["connector-types"],
    queryFn: adminApi.connectorTypes,
  });

  const { data: sourceLanguages = [] } = useQuery({
    queryKey: ["source-languages"],
    queryFn: adminApi.sourceLanguages,
  });

  useEffect(() => {
    if (source) {
      setName(source.name);
      setSourceLanguage(source.source_language || "");
      setEnabled(source.enabled);
      setSchedule(source.schedule || "");
      setPathValue(source.path || "");
      const cfg: Record<string, string> = {};
      for (const [k, v] of Object.entries(source.config)) {
        cfg[k] = String(v ?? "");
      }
      setConfig(cfg);
    }
  }, [source]);

  const currentSpec = connectorTypes.find((c) => c.type === source?.type);

  const updateMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {};
      if (name !== source?.name) payload.name = name;
      if (sourceLanguage !== (source?.source_language || ""))
        payload.source_language = sourceLanguage || null;
      if (enabled !== source?.enabled) payload.enabled = enabled;
      if (schedule !== (source?.schedule || ""))
        payload.schedule = schedule || null;

      const origConfig: Record<string, unknown> = source?.config ?? {};
      const configChanged = Object.keys({ ...origConfig, ...config }).some(
        (k) => String(origConfig[k] ?? "") !== (config[k] ?? "")
      );
      if (configChanged) payload.config = config;

      return adminApi.updateSource(sourceId!, payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-source", sourceId] });
      qc.invalidateQueries({ queryKey: ["sources"] });
      showToast("success", "Source updated.");
      navigate({ to: "/admin/sources/$sourceId", params: { sourceId: sourceId! } });
    },
    onError: () => {
      showToast("error", "Failed to update source.");
    },
  });

  if (isLoading) {
    return (
      <div className={styles.page}>
        <SkeletonRow count={6} />
      </div>
    );
  }

  if (isError || !source) {
    return (
      <div className={styles.page}>
        <EmptyState title="Source not found" body="The source could not be loaded." />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate({ to: "/admin/sources/$sourceId", params: { sourceId: sourceId! } })}
        >
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>Edit: {source.name}</h1>
      </div>

      <div className={styles.section}>
        <h2>Settings</h2>
        <div className={styles.form}>
          <TextInput
            label="Source name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          {currentSpec?.fields.map((f) => (
            <TextInput
              key={f.key}
              label={f.label}
              type={f.sensitive ? "password" : "text"}
              placeholder={f.placeholder}
              value={config[f.key] || ""}
              onChange={(e) =>
                setConfig((c) => ({ ...c, [f.key]: e.target.value }))
              }
            />
          ))}

          {source.path !== null && (
            <TextInput
              label="Path"
              value={pathValue}
              onChange={(e) => {
                setPathValue(e.target.value);
                setConfig((c) => ({ ...c, path: e.target.value }));
              }}
            />
          )}

          <label className={styles.label}>
            Language
            <select
              className={styles.select}
              value={sourceLanguage}
              onChange={(e) => setSourceLanguage(e.target.value)}
            >
              <option value="">Auto detect</option>
              {sourceLanguages.map((code) => (
                <option key={code} value={code}>
                  {code.toUpperCase()}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.label}>
            Schedule (cron)
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. 0 */6 * * *"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
            />
            <span className={styles.mutedMeta}>
              Leave empty for manual sync only. Format: minute hour day month weekday.
            </span>
          </label>

          <label className={styles.label}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />{" "}
            Enabled
          </label>

          <div className={styles.dialogActions}>
            <Button
              onClick={() => updateMutation.mutate()}
              loading={updateMutation.isPending}
              disabled={!name}
            >
              <Save size={14} /> Save changes
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                navigate({ to: "/admin/sources/$sourceId", params: { sourceId: sourceId! } })
              }
            >
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
