import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ServerIcon, Plus } from "lucide-react";
import { adminApi, type SourceGroup } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminSourcesPage.module.css";

type WizardStep = "type" | "settings" | "validate" | "permissions" | "review";

interface WizardState {
  type: string;
  name: string;
  path: string;
  sourceLanguage: string;
  version: string;
  config: Record<string, string>;
  enabled: boolean;
  groups: SourceGroup[];
}

export function AdminAddSourceWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [step, setStep] = useState<WizardStep>("type");
  const [state, setState] = useState<WizardState>({
    type: "", name: "", path: "", sourceLanguage: "en", version: "",
    config: {}, enabled: true, groups: [],
  });

  const { data: connectorTypes = [] } = useQuery({
    queryKey: ["connector-types"],
    queryFn: adminApi.connectorTypes,
  });

  const { data: allGroups = [] } = useQuery({
    queryKey: ["admin-groups"],
    queryFn: adminApi.listGroups,
  });

  const currentSpec = connectorTypes.find((c) => c.type === state.type);

  const createMutation = useMutation({
    mutationFn: () => {
      const config = { ...state.config } as Record<string, string>;
      if (state.version && state.version !== "auto-detect") {
        config["version"] = state.version;
      }
      const payload: Parameters<typeof adminApi.createSource>[0] = {
        name: state.name,
        type: state.type,
        source_language: state.sourceLanguage,
        enabled: state.enabled,
        config,
      };
      if (currentSpec?.fields.some((f) => f.key === "path") && state.path) {
        payload.path = state.path;
      }
      return adminApi.createSource(payload);
    },
    onSuccess: (newSource) => {
      // Grant permissions to selected groups
      const grantPromises = state.groups.map((g) =>
        adminApi.grantPermission(newSource.id, g.id).catch(() => {}),
      );
      Promise.all(grantPromises).then(() => {
        qc.invalidateQueries({ queryKey: ["sources"] });
        showToast("success", "Source created.");
        navigate({ to: "/admin/sources/$sourceId", params: { sourceId: newSource.id } });
      });
    },
    onError: () => showToast("error", "Failed to create source."),
  });

  function update<K extends keyof WizardState>(key: K, value: WizardState[K]) {
    setState((s) => ({ ...s, [key]: value }));
  }

  if (!connectorTypes.length) {
    return <div className={styles.page}><p>Loading connector types...</p></div>;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>Add Source</h1>
      </div>

      <div className={styles.wizardSteps}>
        {(["type", "settings", "validate", "permissions", "review"] as const).map((s, i) => (
          <span key={s} className={`${styles.wizardStep} ${step === s ? styles.wizardStepActive : ""}`}>
            {i + 1}. {s.charAt(0).toUpperCase() + s.slice(1)}
          </span>
        ))}
      </div>

      {step === "type" && (
        <div className={styles.section}>
          <h2>Select source type</h2>
          <div className={styles.typeGrid}>
            {connectorTypes.map((ct) => (
              <button
                key={ct.type}
                className={`${styles.typeCard} ${state.type === ct.type ? styles.typeCardActive : ""}`}
                onClick={() => { update("type", ct.type); setStep("settings"); }}
              >
                <ServerIcon size={24} />
                <span>{ct.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === "settings" && (
        <div className={styles.section}>
          <h2>Connection settings</h2>
          <div className={styles.form}>
            <TextInput label="Source name" {...{value: state.name, onChange: (e: React.ChangeEvent<HTMLInputElement>) => update("name", e.target.value)}} />
            {currentSpec?.fields.map((f) => (
              <TextInput
                key={f.key}
                label={f.label}
                type={f.sensitive ? "password" : "text"}
                {...{value: state.config[f.key] || "", placeholder: f.placeholder,
                  onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
                    update("config", { ...state.config, [f.key]: e.target.value })
                }}
              />
            ))}
            <label className={styles.label}>
              Language
              <select className={styles.select} value={state.sourceLanguage}
                onChange={(e) => update("sourceLanguage", e.target.value)}>
                <option value="en">English</option>
                <option value="fr">French</option>
                <option value="de">German</option>
              </select>
            </label>
            {currentSpec?.supported_versions && (
              <label className={styles.label}>
                Version
                <select className={styles.select} value={state.version}
                  onChange={(e) => update("version", e.target.value)}>
                  <option value="auto-detect">Auto detect</option>
                  {(currentSpec.supported_versions[state.sourceLanguage] || currentSpec.supported_versions["en"] || []).map((v) => (
                    <option key={v.value} value={v.value}>{v.label}</option>
                  ))}
                </select>
              </label>
            )}
            <div className={styles.dialogActions}>
              <Button onClick={() => setStep("validate")} disabled={!state.name}>
                Next: Validate
              </Button>
              <Button variant="secondary" onClick={() => setStep("type")}>Back</Button>
            </div>
          </div>
        </div>
      )}

      {step === "validate" && (
        <div className={styles.section}>
          <h2>Validate connection</h2>
          <p className={styles.mutedMeta}>
            Test the connection before creating the source.
          </p>
          <div className={styles.dialogActions}>
            <Button onClick={() => setStep("permissions")}>
              <Check size={14} /> Skip validation
            </Button>
            <Button variant="secondary" onClick={() => setStep("settings")}>Back</Button>
          </div>
        </div>
      )}

      {step === "permissions" && (
        <div className={styles.section}>
          <h2>Access permissions</h2>
          <p className={styles.mutedMeta}>Choose which groups can access this source.</p>
          <div className={styles.groupList}>
            {allGroups.map((g) => (
              <label key={g.id} className={styles.groupCheckLabel}>
                <input
                  type="checkbox"
                  checked={state.groups.some((sg) => sg.id === g.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      update("groups", [...state.groups, g]);
                    } else {
                      update("groups", state.groups.filter((sg) => sg.id !== g.id));
                    }
                  }}
                />
                {g.name}
              </label>
            ))}
          </div>
          <div className={styles.dialogActions}>
            <Button onClick={() => setStep("review")}>Next: Review</Button>
            <Button variant="secondary" onClick={() => setStep("validate")}>Back</Button>
          </div>
        </div>
      )}

      {step === "review" && (
        <div className={styles.section}>
          <h2>Review and create</h2>
          <dl className={styles.dl}>
            <dt>Type</dt><dd>{state.type}</dd>
            <dt>Name</dt><dd>{state.name}</dd>
            <dt>Language</dt><dd>{state.sourceLanguage}</dd>
            <dt>Enabled</dt><dd>{state.enabled ? "Yes" : "No"}</dd>
            {Object.entries(state.config).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{currentSpec?.fields.find((f) => f.key === k)?.sensitive ? "••••••••" : v}</dd>
              </div>
            ))}
            <dt>Groups</dt>
            <dd>{state.groups.length ? state.groups.map((g) => g.name).join(", ") : "None"}</dd>
          </dl>
          <div className={styles.dialogActions}>
            <Button onClick={() => createMutation.mutate()} loading={createMutation.isPending}>
              <Plus size={14} /> Create source
            </Button>
            <Button variant="secondary" onClick={() => setStep("permissions")}>Back</Button>
          </div>
        </div>
      )}
    </div>
  );
}
