import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Cpu, RotateCcw, Save } from "lucide-react";
import {
  adminApi,
  type SystemConfigEntry,
  type SystemConfigValue,
} from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { Dialog } from "@/components/primitives/Dialog";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminSourcesPage.module.css";

const MASK = "••••••••";

interface ConfigGroup {
  id: string;
  title: string;
  description: string;
  entries: SystemConfigEntry[];
}

/** Ordered group definitions keyed by config-key prefix. */
const GROUP_DEFS: { id: string; title: string; description: string; prefixes: string[] }[] = [
  {
    id: "feature",
    title: "Feature Flags",
    description: "Toggle product surfaces on or off at runtime. Changes apply within ~30s.",
    prefixes: ["feature."],
  },
  {
    id: "llm",
    title: "LLM Model & Prompts",
    description:
      "Default model name and system prompts. For full provider/model management use Model Providers.",
    prefixes: ["llm."],
  },
  {
    id: "model",
    title: "Translation Model Bundles",
    description:
      "Local file-path overrides for the high-quality translation and QE model bundles. Leave blank to use the environment default; applied on the next worker start. Embedding, reranker, and chat models are configured under Model Providers.",
    prefixes: ["model."],
  },
  {
    id: "search",
    title: "Search & Retrieval",
    description: "Hybrid search weighting and related-document limits.",
    prefixes: ["search."],
  },
  {
    id: "other",
    title: "Other Settings",
    description: "Alerting, auto-enrichment, and remaining tunables.",
    prefixes: [],
  },
];

function humanizeKey(key: string): string {
  const tail = key.includes(".") ? key.slice(key.indexOf(".") + 1) : key;
  return tail
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function groupEntries(entries: SystemConfigEntry[]): ConfigGroup[] {
  const sorted = [...entries].sort((a, b) => a.key.localeCompare(b.key));
  return GROUP_DEFS.map((def) => ({
    id: def.id,
    title: def.title,
    description: def.description,
    entries: sorted.filter((e) =>
      def.prefixes.length === 0
        ? !GROUP_DEFS.some(
            (d) => d.prefixes.length > 0 && d.prefixes.some((p) => e.key.startsWith(p)),
          )
        : def.prefixes.some((p) => e.key.startsWith(p)),
    ),
  })).filter((g) => g.entries.length > 0);
}

export function AdminConfigPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();

  const [drafts, setDrafts] = useState<Record<string, SystemConfigValue>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["admin-config"],
    queryFn: adminApi.listConfig,
  });

  const groups = useMemo(() => groupEntries(entries), [entries]);

  const updateMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: SystemConfigValue }) =>
      adminApi.updateConfig(key, value),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["admin-config"] });
      setDrafts((d) => {
        const next = { ...d };
        delete next[vars.key];
        return next;
      });
      showToast("success", `Saved ${vars.key}.`);
    },
    onError: (err: Error) => showToast("error", err.message),
    onSettled: () => setSavingKey(null),
  });

  const resetMutation = useMutation({
    mutationFn: adminApi.resetConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-config"] });
      setDrafts({});
      setResetOpen(false);
      showToast("success", "Configuration reset to defaults.");
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  function currentValue(entry: SystemConfigEntry): SystemConfigValue {
    return entry.key in drafts ? drafts[entry.key] : entry.value;
  }

  function isDirty(entry: SystemConfigEntry): boolean {
    return entry.key in drafts && drafts[entry.key] !== entry.value;
  }

  function setDraft(key: string, value: SystemConfigValue) {
    setDrafts((d) => ({ ...d, [key]: value }));
  }

  function handleSave(entry: SystemConfigEntry) {
    setSavingKey(entry.key);
    updateMutation.mutate({ key: entry.key, value: currentValue(entry) });
  }

  function renderControl(entry: SystemConfigEntry) {
    const value = currentValue(entry);

    if (typeof value === "boolean") {
      return (
        <label className={styles.groupCheckLabel}>
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => setDraft(entry.key, e.target.checked)}
          />
          {value ? "Enabled" : "Disabled"}
        </label>
      );
    }

    if (value === MASK) {
      return <span className={styles.mutedMeta}>Hidden (sensitive value)</span>;
    }

    if (typeof value === "number") {
      return (
        <input
          className={styles.input}
          type="number"
          step="any"
          value={value}
          onChange={(e) =>
            setDraft(entry.key, e.target.value === "" ? 0 : Number(e.target.value))
          }
        />
      );
    }

    // String — prompts get a multi-line editor.
    if (entry.key.includes("prompt")) {
      return (
        <textarea
          className={styles.input}
          rows={3}
          value={value}
          onChange={(e) => setDraft(entry.key, e.target.value)}
        />
      );
    }
    return (
      <input
        className={styles.input}
        type="text"
        value={value}
        onChange={(e) => setDraft(entry.key, e.target.value)}
      />
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Admin
        </Button>
        <h1 className={styles.title}>Configuration</h1>
        <div className={styles.actions}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate({ to: "/admin/model-providers" })}
          >
            <Cpu size={14} />
            Model Providers
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setResetOpen(true)}>
            <RotateCcw size={14} />
            Reset to defaults
          </Button>
        </div>
      </div>

      {isLoading ? (
        <SkeletonRow count={6} className={styles.skeletons} />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={<Cpu size={32} />}
          title="No configuration available"
          body="No editable system configuration keys were returned."
        />
      ) : (
        groups.map((group) => (
          <section key={group.id} style={{ marginBottom: "28px" }}>
            <h2
              className={styles.title}
              style={{ fontSize: "var(--font-size-section-title)", marginBottom: "4px" }}
            >
              {group.title}
            </h2>
            <p className={styles.mutedMeta} style={{ marginBottom: "10px" }}>
              {group.description}
            </p>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th style={{ width: "32%" }}>Setting</th>
                    <th>Value</th>
                    <th style={{ width: "120px" }}>State</th>
                    <th style={{ width: "100px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {group.entries.map((entry) => (
                    <tr key={entry.key}>
                      <td className={styles.nameCell}>
                        {humanizeKey(entry.key)}
                        <div className={styles.mutedMeta}>{entry.key}</div>
                      </td>
                      <td>{renderControl(entry)}</td>
                      <td>
                        {entry.is_default ? (
                          <Badge variant="neutral">Default</Badge>
                        ) : (
                          <Badge variant="warning">Overridden</Badge>
                        )}
                      </td>
                      <td>
                        <Button
                          size="sm"
                          disabled={!isDirty(entry) || currentValue(entry) === MASK}
                          loading={savingKey === entry.key}
                          onClick={() => handleSave(entry)}
                        >
                          <Save size={13} />
                          Save
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}

      <Dialog
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        title="Reset configuration to defaults"
      >
        <p style={{ marginBottom: "16px", color: "var(--color-text-secondary)" }}>
          This restores every system configuration value to its registered default and
          discards all admin overrides. This cannot be undone.
        </p>
        <div className={styles.dialogActions}>
          <Button
            variant="danger"
            onClick={() => resetMutation.mutate()}
            loading={resetMutation.isPending}
          >
            <RotateCcw size={14} />
            Reset all
          </Button>
          <Button variant="secondary" onClick={() => setResetOpen(false)}>
            Cancel
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
