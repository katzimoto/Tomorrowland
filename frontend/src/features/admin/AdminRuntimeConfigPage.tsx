import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, RotateCcw, Search } from "lucide-react";
import {
  adminApi,
  type RuntimeConfigSetting,
  type RuntimeConfigValue,
} from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminRuntimeConfigPage.module.css";

const SOURCE_LABELS: Record<RuntimeConfigSetting["source"], string> = {
  default: "Default",
  env: "Environment",
  database_override: "DB override",
};

function restartNote(s: RuntimeConfigSetting): string | null {
  if (s.requires_reindex) return "Requires document reindex";
  if (s.requires_resync) return "Requires source resync";
  if (s.requires_worker_restart) return "Requires worker restart";
  if (s.requires_restart) return "Requires API restart";
  return null;
}

function displayValue(s: RuntimeConfigSetting): string {
  const v = s.current_effective_value;
  if (v === null || v === undefined) return s.is_secret ? "Not set" : "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

interface RowProps {
  setting: RuntimeConfigSetting;
  onSave: (key: string, value: RuntimeConfigValue) => void;
  onReset: (key: string) => void;
  saving: boolean;
}

function ConfigRow({ setting, onSave, onReset, saving }: RowProps) {
  const effective = setting.current_effective_value ?? null;
  const [draft, setDraft] = useState<RuntimeConfigValue>(effective);
  const note = restartNote(setting);
  const dirty =
    setting.is_runtime_editable && !setting.is_secret && draft !== effective;

  const editor = () => {
    if (!setting.is_runtime_editable || setting.is_secret) return null;
    if (setting.type === "bool") {
      return (
        <label className={styles.boolLabel}>
          <input
            type="checkbox"
            checked={Boolean(draft)}
            onChange={(e) => setDraft(e.target.checked)}
          />
          {draft ? "Enabled" : "Disabled"}
        </label>
      );
    }
    if (setting.type === "enum") {
      return (
        <select
          className={styles.select}
          value={String(draft ?? "")}
          onChange={(e) => setDraft(e.target.value)}
          aria-label={`${setting.display_name} value`}
        >
          {(setting.enum_values ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    }
    if (setting.type === "int" || setting.type === "float") {
      return (
        <input
          type="number"
          className={styles.input}
          value={draft === null ? "" : Number(draft)}
          step={setting.type === "float" ? "0.01" : "1"}
          min={setting.min_value ?? undefined}
          max={setting.max_value ?? undefined}
          onChange={(e) =>
            setDraft(e.target.value === "" ? null : Number(e.target.value))
          }
          aria-label={`${setting.display_name} value`}
        />
      );
    }
    return (
      <input
        type="text"
        className={styles.input}
        value={String(draft ?? "")}
        onChange={(e) => setDraft(e.target.value)}
        aria-label={`${setting.display_name} value`}
      />
    );
  };

  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.rowHead}>
          <span className={styles.settingName}>{setting.display_name}</span>
          <code className={styles.settingKey}>{setting.key}</code>
          <Badge variant="neutral">{SOURCE_LABELS[setting.source]}</Badge>
          {setting.is_secret && <Badge variant="warning">secret</Badge>}
          {!setting.is_runtime_editable && !setting.is_secret && (
            <Badge variant="neutral">read-only</Badge>
          )}
        </div>
        <p className={styles.settingDesc}>{setting.description}</p>
        <div className={styles.metaLine}>
          <span>
            Effective: <strong>{displayValue(setting)}</strong>
          </span>
          {!setting.is_secret && setting.safe_default !== undefined && (
            <span className={styles.muted}>
              Default: {String(setting.safe_default)}
            </span>
          )}
          {note && <Badge variant="warning">{note}</Badge>}
        </div>
      </div>
      <div className={styles.rowControls}>
        {editor()}
        {setting.is_runtime_editable && !setting.is_secret && (
          <div className={styles.rowActions}>
            <Button
              size="sm"
              variant="primary"
              disabled={!dirty || saving}
              onClick={() => onSave(setting.key, draft)}
            >
              Save
            </Button>
            {setting.override_present && (
              <Button
                size="sm"
                variant="ghost"
                disabled={saving}
                onClick={() => onReset(setting.key)}
              >
                Reset
              </Button>
            )}
          </div>
        )}
        {dirty && note && (
          <span className={styles.dirtyWarn} role="alert">
            {note} for this change to take effect.
          </span>
        )}
      </div>
    </div>
  );
}

export function AdminRuntimeConfigPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [filter, setFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["runtime-config"],
    queryFn: adminApi.listRuntimeConfig,
  });
  const { data: audit } = useQuery({
    queryKey: ["runtime-config-audit"],
    queryFn: adminApi.runtimeConfigAudit,
  });

  const saveMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: RuntimeConfigValue }) =>
      adminApi.updateRuntimeConfig(key, value),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["runtime-config"] });
      qc.invalidateQueries({ queryKey: ["runtime-config-audit"] });
      showToast("success", `Saved ${vars.key}.`);
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  const resetMutation = useMutation({
    mutationFn: (key: string) => adminApi.resetRuntimeConfig(key),
    onSuccess: (_res, key) => {
      qc.invalidateQueries({ queryKey: ["runtime-config"] });
      qc.invalidateQueries({ queryKey: ["runtime-config-audit"] });
      showToast("success", `Reset ${key} to default.`);
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  const reloadMutation = useMutation({
    mutationFn: adminApi.reloadRuntimeConfig,
    onSuccess: (res) => showToast("success", res.note),
    onError: (err: Error) => showToast("error", err.message),
  });

  const grouped = useMemo(() => {
    const settings = data?.settings ?? [];
    const q = filter.trim().toLowerCase();
    const matched = q
      ? settings.filter(
          (s) =>
            s.key.toLowerCase().includes(q) ||
            s.display_name.toLowerCase().includes(q) ||
            s.category.toLowerCase().includes(q),
        )
      : settings;
    const byCategory = new Map<string, RuntimeConfigSetting[]>();
    for (const s of matched) {
      const list = byCategory.get(s.category) ?? [];
      list.push(s);
      byCategory.set(s.category, list);
    }
    return Array.from(byCategory.entries());
  }, [data, filter]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.back}
          onClick={() => navigate({ to: "/admin" })}
          aria-label="Back to admin"
        >
          <ArrowLeft size={18} />
        </button>
        <h1 className={styles.title}>Runtime Configuration</h1>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => reloadMutation.mutate()}
          disabled={reloadMutation.isPending}
        >
          <RefreshCw size={14} /> Reload
        </Button>
      </div>

      {data?.precedence && (
        <p className={styles.precedence}>
          <RotateCcw size={14} /> Precedence: {data.precedence}
        </p>
      )}

      <div className={styles.searchWrap}>
        <Search size={16} className={styles.searchIcon} />
        <input
          className={styles.search}
          placeholder="Filter by key, name, or category…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Filter settings"
        />
      </div>

      {isLoading && (
        <div className={styles.skeletons}>
          <SkeletonRow count={6} />
        </div>
      )}

      {!isLoading && grouped.length === 0 && (
        <EmptyState
          title="No settings match"
          body="Try a different filter term."
        />
      )}

      {!isLoading &&
        grouped.map(([category, settings]) => (
          <section key={category} className={styles.category}>
            <h2 className={styles.categoryTitle}>{category}</h2>
            {settings.map((s) => (
              <ConfigRow
                key={s.key}
                setting={s}
                saving={saveMutation.isPending || resetMutation.isPending}
                onSave={(key, value) => saveMutation.mutate({ key, value })}
                onReset={(key) => resetMutation.mutate(key)}
              />
            ))}
          </section>
        ))}

      {audit && audit.length > 0 && (
        <section className={styles.category}>
          <h2 className={styles.categoryTitle}>Recent changes</h2>
          <ul className={styles.auditList}>
            {audit.map((entry) => (
              <li key={entry.id} className={styles.auditItem}>
                <Badge variant="neutral">{entry.action}</Badge>
                <code className={styles.settingKey}>{entry.key ?? "—"}</code>
                <span className={styles.muted}>{entry.created_at}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default AdminRuntimeConfigPage;
