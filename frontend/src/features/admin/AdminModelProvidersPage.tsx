import { useCallback, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  FlaskConical,
  Plus,
  Search,
  Server,
  Trash2,
  XCircle,
  RefreshCw,
} from "lucide-react";
import { adminApi, type ModelProvider, type ModelDescriptor, type ModelTaskDefault, type ProviderDiscoverResult } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { TextInput } from "@/components/primitives/TextInput";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./AdminSourcesPage.module.css";

const PROVIDER_TYPES = [
  { value: "ollama", label: "Ollama" },
  { value: "openai-compatible", label: "OpenAI Compatible" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "litellm", label: "LiteLLM" },
  { value: "llama-cpp", label: "llama.cpp" },
];

const LOCALITY_OPTIONS = [
  { value: "local", label: "Local", desc: "Runs on this machine (localhost)" },
  { value: "self_hosted", label: "Self-hosted", desc: "Runs on your own infrastructure" },
  { value: "external", label: "External", desc: "Third-party SaaS / cloud API" },
];

const TASK_TYPES = [
  "chat",
  "utility",
  "reranking",
  "embedding",
  "classification",
  "extraction",
];

const DESCRIPTOR_FIELDS = [
  { key: "model_name", label: "Model Name", required: true },
  { key: "display_name", label: "Display Name", required: false },
  { key: "description", label: "Description", required: false },
  { key: "context_window", label: "Context Window", required: false, type: "number" },
  { key: "max_output_tokens", label: "Max Output Tokens", required: false, type: "number" },
] as const;

function localityBadge(locality: string) {
  const variant =
    locality === "local" ? "success" : locality === "self_hosted" ? "warning" : "neutral";
  return <Badge variant={variant}>{locality}</Badge>;
}

export function AdminModelProvidersPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ModelProvider | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelProvider | null>(null);
  const [descriptorProvider, setDescriptorProvider] = useState<ModelProvider | null>(null);
  const [descriptorEdit, setDescriptorEdit] = useState<ModelDescriptor | null>(null);
  const [taskDefaultEdit, setTaskDefaultEdit] = useState<ModelTaskDefault | null>(null);

  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [discoverResults, setDiscoverResults] = useState<Record<string, ProviderDiscoverResult[] | string>>({});

  // --- Create form state ---
  const [createName, setCreateName] = useState("");
  const [createType, setCreateType] = useState("ollama");
  const [createBaseUrl, setCreateBaseUrl] = useState("");
  const [createCredential, setCreateCredential] = useState("");
  const [createLocality, setCreateLocality] = useState("local");
  const [createEnabled, setCreateEnabled] = useState(true);
  const [createError, setCreateError] = useState("");

  // --- Edit form state ---
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState("ollama");
  const [editBaseUrl, setEditBaseUrl] = useState("");
  const [editCredential, setEditCredential] = useState("");
  const [editClearCredential, setEditClearCredential] = useState(false);
  const [editLocality, setEditLocality] = useState("local");
  const [editEnabled, setEditEnabled] = useState(true);
  const [editError, setEditError] = useState("");

  // --- Descriptor form state ---
  const [descModelName, setDescModelName] = useState("");
  const [descDisplayName, setDescDisplayName] = useState("");
  const [descDescription, setDescDescription] = useState("");
  const [descContextWindow, setDescContextWindow] = useState("");
  const [descMaxTokens, setDescMaxTokens] = useState("");
  const [descError, setDescError] = useState("");

  // --- Task default form state ---
  const [tdTaskType, setTdTaskType] = useState("chat");
  const [tdProviderId, setTdProviderId] = useState("");
  const [tdDescriptorId, setTdDescriptorId] = useState("");
  const [tdError, setTdError] = useState("");

  // --- Queries ---
  const { data: providers = [], isLoading: providersLoading } = useQuery({
    queryKey: ["model-providers"],
    queryFn: adminApi.listModelProviders,
  });

  const { data: taskDefaults = [], isLoading: tdLoading } = useQuery({
    queryKey: ["model-task-defaults"],
    queryFn: adminApi.listTaskDefaults,
  });

  const { data: descriptors = [] } = useQuery({
    queryKey: ["model-descriptors", descriptorProvider?.id],
    queryFn: () => adminApi.listModelDescriptors(descriptorProvider!.id),
    enabled: !!descriptorProvider,
  });

  // --- Mutations ---
  const createMutation = useMutation({
    mutationFn: adminApi.createModelProvider,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-providers"] });
      setCreateOpen(false);
      resetCreateForm();
      showToast("success", "Provider created.");
    },
    onError: (err: Error) => setCreateError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateModelProvider(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-providers"] });
      setEditTarget(null);
      showToast("success", "Provider updated.");
    },
    onError: (err: Error) => setEditError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteModelProvider(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-providers"] });
      setDeleteTarget(null);
      showToast("success", "Provider deleted.");
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  const descCreateMutation = useMutation({
    mutationFn: ({ providerId, payload }: { providerId: string; payload: Record<string, unknown> }) =>
      adminApi.createModelDescriptor(providerId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-descriptors", descriptorProvider?.id] });
      resetDescForm();
      showToast("success", "Descriptor added.");
    },
    onError: (err: Error) => setDescError(err.message),
  });

  const descUpdateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateModelDescriptor(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-descriptors", descriptorProvider?.id] });
      setDescriptorEdit(null);
      resetDescForm();
      showToast("success", "Descriptor updated.");
    },
    onError: (err: Error) => setDescError(err.message),
  });

  const descDeleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteModelDescriptor(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-descriptors", descriptorProvider?.id] });
      showToast("success", "Descriptor deleted.");
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  const tdMutation = useMutation({
    mutationFn: ({ taskType, payload }: { taskType: string; payload: { provider_id: string; model_descriptor_id?: string | null } }) =>
      adminApi.setTaskDefault(taskType, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-task-defaults"] });
      setTaskDefaultEdit(null);
      resetTdForm();
      showToast("success", "Task default saved.");
    },
    onError: (err: Error) => setTdError(err.message),
  });

  const tdDeleteMutation = useMutation({
    mutationFn: (taskType: string) => adminApi.deleteTaskDefault(taskType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-task-defaults"] });
      showToast("success", "Task default removed.");
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  const reloadMutation = useMutation({
    mutationFn: adminApi.reloadModelProviders,
    onSuccess: () => showToast("success", "Providers reloaded into runtime."),
    onError: (err: Error) => showToast("error", err.message),
  });

  // --- Form helpers ---
  function resetCreateForm() {
    setCreateName("");
    setCreateType("ollama");
    setCreateBaseUrl("");
    setCreateCredential("");
    setCreateLocality("local");
    setCreateEnabled(true);
    setCreateError("");
  }

  function resetEditForm() {
    setEditName("");
    setEditType("ollama");
    setEditBaseUrl("");
    setEditCredential("");
    setEditClearCredential(false);
    setEditLocality("local");
    setEditEnabled(true);
    setEditError("");
  }

  function resetDescForm() {
    setDescModelName("");
    setDescDisplayName("");
    setDescDescription("");
    setDescContextWindow("");
    setDescMaxTokens("");
    setDescError("");
  }

  function resetTdForm() {
    setTdTaskType("chat");
    setTdProviderId("");
    setTdDescriptorId("");
    setTdError("");
  }

  function openEditDialog(p: ModelProvider) {
    setEditTarget(p);
    setEditName(p.name);
    setEditType(p.provider_type);
    setEditBaseUrl(p.base_url ?? "");
    setEditCredential("");
    setEditClearCredential(false);
    setEditLocality(p.locality);
    setEditEnabled(p.enabled);
    setEditError("");
  }

  function openDescriptorEdit(d: ModelDescriptor) {
    setDescriptorEdit(d);
    setDescModelName(d.model_name);
    setDescDisplayName(d.display_name ?? "");
    setDescDescription(d.description ?? "");
    setDescContextWindow(d.context_window != null ? String(d.context_window) : "");
    setDescMaxTokens(d.max_output_tokens != null ? String(d.max_output_tokens) : "");
    setDescError("");
  }

  function openTdEdit(td: ModelTaskDefault) {
    setTaskDefaultEdit(td);
    setTdTaskType(td.task_type);
    setTdProviderId(td.provider_id);
    setTdDescriptorId(td.model_descriptor_id ?? "");
    setTdError("");
  }

  // --- Actions ---
  const handleCreate = useCallback(async () => {
    if (!createName.trim()) { setCreateError("Name is required."); return; }
    setCreateError("");
    await createMutation.mutateAsync({
      name: createName.trim(),
      provider_type: createType,
      base_url: createBaseUrl.trim() || null,
      credential_value: createCredential.trim() || null,
      locality: createLocality,
      enabled: createEnabled,
    });
  }, [createName, createType, createBaseUrl, createCredential, createLocality, createEnabled, createMutation]);

  const handleEdit = useCallback(async () => {
    if (!editTarget || !editName.trim()) { setEditError("Name is required."); return; }
    setEditError("");
    const payload: Record<string, unknown> = {
      name: editName.trim(),
      provider_type: editType,
      base_url: editBaseUrl.trim() || null,
      locality: editLocality,
      enabled: editEnabled,
    };
    if (editCredential.trim()) {
      payload.credential_value = editCredential.trim();
    }
    if (editClearCredential) {
      payload.credential_value = "";
    }
    await updateMutation.mutateAsync({ id: editTarget.id, payload });
  }, [editTarget, editName, editType, editBaseUrl, editCredential, editClearCredential, editLocality, editEnabled, updateMutation]);

  const handleTest = useCallback(async (provider: ModelProvider) => {
    setTestResults((r) => ({ ...r, [provider.id]: "testing" }));
    try {
      const result = await adminApi.testModelProvider(provider.id);
      if (result.healthy) {
        setTestResults((r) => ({ ...r, [provider.id]: `Healthy (${result.latency_ms?.toFixed(0) ?? "?"}ms)` }));
      } else {
        setTestResults((r) => ({ ...r, [provider.id]: result.error ?? "Unhealthy" }));
      }
    } catch (err) {
      setTestResults((r) => ({ ...r, [provider.id]: err instanceof Error ? err.message : "Test failed" }));
    }
  }, []);

  const handleDiscover = useCallback(async (provider: ModelProvider) => {
    setDiscoverResults((r) => ({ ...r, [provider.id]: "discovering" }));
    try {
      const models = await adminApi.discoverModels(provider.id);
      setDiscoverResults((r) => ({ ...r, [provider.id]: models }));
    } catch (err) {
      setDiscoverResults((r) => ({ ...r, [provider.id]: err instanceof Error ? err.message : "Discovery failed" }));
    }
  }, []);

  const handleCreateDescriptor = useCallback(async () => {
    if (!descModelName.trim()) { setDescError("Model name is required."); return; }
    if (!descriptorProvider) return;
    setDescError("");
    const payload: Record<string, unknown> = { model_name: descModelName.trim() };
    if (descDisplayName.trim()) payload.display_name = descDisplayName.trim();
    if (descDescription.trim()) payload.description = descDescription.trim();
    if (descContextWindow.trim()) payload.context_window = Number(descContextWindow.trim());
    if (descMaxTokens.trim()) payload.max_output_tokens = Number(descMaxTokens.trim());
    if (descriptorEdit) {
      await descUpdateMutation.mutateAsync({ id: descriptorEdit.id, payload });
    } else {
      await descCreateMutation.mutateAsync({ providerId: descriptorProvider.id, payload });
    }
  }, [descModelName, descDisplayName, descDescription, descContextWindow, descMaxTokens, descriptorProvider, descriptorEdit, descCreateMutation, descUpdateMutation]);

  const handleSaveTaskDefault = useCallback(async () => {
    if (!tdProviderId.trim()) { setTdError("Provider is required."); return; }
    setTdError("");
    const taskType = taskDefaultEdit ? taskDefaultEdit.task_type : tdTaskType;
    await tdMutation.mutateAsync({
      taskType,
      payload: {
        provider_id: tdProviderId.trim(),
        model_descriptor_id: tdDescriptorId.trim() || null,
      },
    });
  }, [tdTaskType, tdProviderId, tdDescriptorId, taskDefaultEdit, tdMutation]);

  // --- Render helpers ---
  function renderTestResult(providerId: string) {
    const r = testResults[providerId];
    if (!r) return null;
    if (r === "testing") return null;
    const isOk = !r.startsWith("Healthy");
    return (
      <p className={`${styles.syncResult} ${isOk ? styles.syncError : styles.syncOk}`}>
        {isOk ? <XCircle size={13} /> : <CheckCircle2 size={13} />}
        {r}
      </p>
    );
  }

  function renderDiscoverResult(providerId: string) {
    const r = discoverResults[providerId];
    if (!r) return null;
    if (r === "discovering") return <span className={styles.mutedMeta}>Discovering...</span>;
    if (typeof r === "string") return <span className={styles.syncError}>{r}</span>;
    if (r.length === 0) return <span className={styles.mutedMeta}>No models found</span>;
    return (
      <div className={styles.syncSummary}>
        <span className={styles.syncOk}>{r.length} model{r.length !== 1 ? "s" : ""} found</span>
      </div>
    );
  }

  function renderEditCredentialField() {
    if (!editTarget) return null;
    return (
      <div className={styles.field}>
        <label className={styles.label}>Credential</label>
        {editTarget.credential_set && !editClearCredential && (
          <p className={styles.mutedMeta}>Stored credential is set. Enter a new value to replace it.</p>
        )}
        <input
          className={styles.input}
          type="password"
          value={editCredential}
          onChange={(e) => setEditCredential(e.target.value)}
          placeholder={editTarget.credential_set ? "New credential value (leave empty to keep existing)" : "API key or token"}
          autoComplete="new-password"
        />
        {editTarget.credential_set && (
          <label className={styles.groupCheckLabel} style={{ marginTop: "4px" }}>
            <input
              type="checkbox"
              checked={editClearCredential}
              onChange={(e) => setEditClearCredential(e.target.checked)}
            />
            Clear stored credential
          </label>
        )}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* --- Header --- */}
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Admin
        </Button>
        <h1 className={styles.title}>Model Providers</h1>
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" onClick={() => reloadMutation.mutate()} loading={reloadMutation.isPending}>
            <RefreshCw size={14} />
            Reload
          </Button>
          <Button onClick={() => { resetCreateForm(); setCreateOpen(true); }}>
            <Plus size={16} />
            Add Provider
          </Button>
        </div>
      </div>

      {/* --- Provider List --- */}
      {providersLoading ? (
        <SkeletonRow count={3} className={styles.skeletons} />
      ) : providers.length === 0 ? (
        <EmptyState
          icon={<Server size={32} />}
          title="No model providers configured"
          body="Add a provider like Ollama, OpenAI, or any OpenAI-compatible endpoint to enable LLM features."
          action={
            <Button onClick={() => { resetCreateForm(); setCreateOpen(true); }}>
              <Plus size={16} />
              Add Provider
            </Button>
          }
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Locality</th>
                <th>Status</th>
                <th>Credential</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id}>
                  <td className={styles.nameCell}>{p.name}</td>
                  <td><Badge variant="neutral">{p.provider_type}</Badge></td>
                  <td>{localityBadge(p.locality)}</td>
                  <td>
                    {p.enabled ? (
                      <Badge variant="success">Active</Badge>
                    ) : (
                      <Badge variant="danger">Disabled</Badge>
                    )}
                  </td>
                  <td>
                    {p.credential_set ? (
                      <Badge variant="warning">Set</Badge>
                    ) : (
                      <span className={styles.mutedMeta}>Not set</span>
                    )}
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <Button variant="secondary" size="sm" onClick={() => handleTest(p)} loading={testResults[p.id] === "testing"}>
                        <FlaskConical size={13} />
                        Test
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => handleDiscover(p)} loading={discoverResults[p.id] === "discovering"}>
                        <Search size={13} />
                        Discover
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => setDescriptorProvider(p)}>
                        <Server size={13} />
                        Models
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => openEditDialog(p)}>
                        Edit
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => setDeleteTarget(p)}>
                        <Trash2 size={13} />
                      </Button>
                    </div>
                    {renderTestResult(p.id)}
                    {renderDiscoverResult(p.id)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* --- Task Defaults Section --- */}
      <h2 className={styles.title} style={{ marginTop: "32px", fontSize: "var(--font-size-section-title)" }}>
        Task Defaults
      </h2>
      {tdLoading ? (
        <SkeletonRow count={2} className={styles.skeletons} />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Task Type</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {taskDefaults.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", padding: "24px", color: "var(--color-text-muted)" }}>
                    No task defaults configured. System will use env/config fallbacks.
                  </td>
                </tr>
              ) : (
                taskDefaults.map((td) => {
                  const prov = providers.find((p) => p.id === td.provider_id);
                  const desc = descriptors.find((d) => d.id === td.model_descriptor_id);
                  return (
                    <tr key={td.task_type}>
                      <td><Badge variant="tag">{td.task_type}</Badge></td>
                      <td>{prov?.name ?? td.provider_id.slice(0, 8)}</td>
                      <td>{desc?.model_name ?? td.model_descriptor_id?.slice(0, 8) ?? "—"}</td>
                      <td>
                        <div className={styles.actions}>
                          <Button variant="secondary" size="sm" onClick={() => openTdEdit(td)}>Edit</Button>
                          <Button variant="secondary" size="sm" onClick={() => {
                            if (confirm(`Remove task default for "${td.task_type}"? System will fall back to env/config.`)) {
                              tdDeleteMutation.mutate(td.task_type);
                            }
                          }}><Trash2 size={13} /></Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ marginTop: "8px" }}>
        <Button size="sm" onClick={() => { resetTdForm(); setTaskDefaultEdit(null); }}>
          <Plus size={14} />
          Add Task Default
        </Button>
      </div>

      {/* --- Create Dialog --- */}
      <Dialog open={createOpen} onClose={() => { setCreateOpen(false); resetCreateForm(); }} title="Add Model Provider">
        <form className={styles.form} onSubmit={(e) => { e.preventDefault(); handleCreate(); }} noValidate>
          <TextInput label="Name" value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="My Ollama" required />
          <div className={styles.field}>
            <label className={styles.label} htmlFor="prov-type">Provider Type</label>
            <select id="prov-type" className={styles.select} value={createType} onChange={(e) => setCreateType(e.target.value)}>
              {PROVIDER_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <TextInput label="Base URL" value={createBaseUrl} onChange={(e) => setCreateBaseUrl(e.target.value)} placeholder="http://localhost:11434" />
          <TextInput label="API Key (credential)" type="password" value={createCredential} onChange={(e) => setCreateCredential(e.target.value)} placeholder="Optional API key or token" autoComplete="new-password" />
          <div className={styles.field}>
            <label className={styles.label} htmlFor="prov-locality">Locality</label>
            <select id="prov-locality" className={styles.select} value={createLocality} onChange={(e) => setCreateLocality(e.target.value)}>
              {LOCALITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label} — {o.desc}</option>)}
            </select>
          </div>
          <label className={styles.groupCheckLabel}>
            <input type="checkbox" checked={createEnabled} onChange={(e) => setCreateEnabled(e.target.checked)} />
            Enabled
          </label>
          {createError && <p className={styles.formError} role="alert">{createError}</p>}
          <div className={styles.dialogActions}>
            <Button type="submit" loading={createMutation.isPending}>Create Provider</Button>
            <Button type="button" variant="secondary" onClick={() => { setCreateOpen(false); resetCreateForm(); }}>Cancel</Button>
          </div>
        </form>
      </Dialog>

      {/* --- Edit Dialog --- */}
      <Dialog open={!!editTarget} onClose={() => { setEditTarget(null); resetEditForm(); }} title={`Edit Provider: ${editTarget?.name ?? ""}`}>
        <form className={styles.form} onSubmit={(e) => { e.preventDefault(); handleEdit(); }} noValidate>
          <TextInput label="Name" value={editName} onChange={(e) => setEditName(e.target.value)} required />
          <div className={styles.field}>
            <label className={styles.label} htmlFor="edit-type">Provider Type</label>
            <select id="edit-type" className={styles.select} value={editType} onChange={(e) => setEditType(e.target.value)}>
              {PROVIDER_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <TextInput label="Base URL" value={editBaseUrl} onChange={(e) => setEditBaseUrl(e.target.value)} placeholder="http://localhost:11434" />
          <div className={styles.field}>
            <label className={styles.label} htmlFor="edit-locality">Locality</label>
            <select id="edit-locality" className={styles.select} value={editLocality} onChange={(e) => setEditLocality(e.target.value)}>
              {LOCALITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label} — {o.desc}</option>)}
            </select>
          </div>
          {renderEditCredentialField()}
          <label className={styles.groupCheckLabel}>
            <input type="checkbox" checked={editEnabled} onChange={(e) => setEditEnabled(e.target.checked)} />
            Enabled
          </label>
          {editError && <p className={styles.formError} role="alert">{editError}</p>}
          <div className={styles.dialogActions}>
            <Button type="submit" loading={updateMutation.isPending}>Save Changes</Button>
            <Button type="button" variant="secondary" onClick={() => { setEditTarget(null); resetEditForm(); }}>Cancel</Button>
          </div>
        </form>
      </Dialog>

      {/* --- Delete Confirmation Dialog --- */}
      <Dialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title={`Delete Provider: ${deleteTarget?.name ?? ""}`}
      >
        <p style={{ marginBottom: "16px", color: "var(--color-text-secondary)" }}>
          Are you sure you want to delete provider <strong>{deleteTarget?.name}</strong>?
          This will remove all associated model descriptors and cannot be undone.
        </p>
        {deleteTarget && (
          <div className={styles.dialogActions}>
            <Button variant="danger" onClick={() => deleteMutation.mutate(deleteTarget.id)} loading={deleteMutation.isPending}>
              <Trash2 size={14} />
              Delete Provider
            </Button>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancel</Button>
          </div>
        )}
      </Dialog>

      {/* --- Model Descriptors Dialog --- */}
      <Dialog
        open={!!descriptorProvider}
        onClose={() => { setDescriptorProvider(null); setDescriptorEdit(null); resetDescForm(); }}
        title={`Models: ${descriptorProvider?.name ?? ""}`}
        width="620px"
      >
        {/* Descriptor list */}
        {descriptors.length === 0 ? (
          <p className={styles.mutedMeta} style={{ marginBottom: "16px" }}>No model descriptors yet.</p>
        ) : (
          <div className={styles.tableWrap} style={{ marginBottom: "16px" }}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Model Name</th>
                  <th>Display Name</th>
                  <th>Context</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {descriptors.map((d) => (
                  <tr key={d.id}>
                    <td className={styles.nameCell}>{d.model_name}</td>
                    <td className={styles.mutedMeta}>{d.display_name ?? "—"}</td>
                    <td className={styles.mutedMeta}>{d.context_window ? `${(d.context_window / 1024).toFixed(0)}K` : "—"}</td>
                    <td>{d.enabled ? <Badge variant="success">Active</Badge> : <Badge variant="danger">Disabled</Badge>}</td>
                    <td>
                      <div className={styles.actions}>
                        <Button variant="secondary" size="sm" onClick={() => openDescriptorEdit(d)}>Edit</Button>
                        <Button variant="secondary" size="sm" onClick={() => {
                          if (confirm(`Delete descriptor "${d.model_name}"?`)) {
                            descDeleteMutation.mutate(d.id);
                          }
                        }}><Trash2 size={13} /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Descriptor form */}
        <h3 style={{ fontSize: "var(--font-size-section-title)", margin: "0 0 12px", color: "var(--color-text-primary)" }}>
          {descriptorEdit ? "Edit Descriptor" : "Add Descriptor"}
        </h3>
        <form className={styles.form} onSubmit={(e) => { e.preventDefault(); handleCreateDescriptor(); }} noValidate>
          {DESCRIPTOR_FIELDS.map((f) => (
            f.key === "model_name" || f.key === "display_name" || f.key === "description" ? (
              <TextInput
                key={f.key}
                label={f.label + (f.required ? "" : " (optional)")}
                value={
                  f.key === "model_name" ? descModelName
                  : f.key === "display_name" ? descDisplayName
                  : descDescription
                }
                onChange={(e) => {
                  const v = e.target.value;
                  if (f.key === "model_name") setDescModelName(v);
                  else if (f.key === "display_name") setDescDisplayName(v);
                  else setDescDescription(v);
                }}
                placeholder={f.key === "model_name" ? "llama3.2" : f.key === "display_name" ? "Llama 3.2" : "Optional description"}
                required={f.required}
              />
            ) : (
              <TextInput
                key={f.key}
                label={f.label + " (optional)"}
                type="number"
                value={
                  f.key === "context_window" ? descContextWindow : descMaxTokens
                }
                onChange={(e) => {
                  const v = e.target.value;
                  if (f.key === "context_window") setDescContextWindow(v);
                  else setDescMaxTokens(v);
                }}
                placeholder={f.key === "context_window" ? "8192" : "2048"}
              />
            )
          ))}
          {descError && <p className={styles.formError} role="alert">{descError}</p>}
          <div className={styles.dialogActions}>
            <Button type="submit" loading={descCreateMutation.isPending || descUpdateMutation.isPending}>
              {descriptorEdit ? "Update Descriptor" : "Add Descriptor"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => { setDescriptorEdit(null); resetDescForm(); }}>
              {descriptorEdit ? "Cancel Edit" : "Clear"}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* --- Task Default Dialog --- */}
      <Dialog
        open={!!taskDefaultEdit || false}
        onClose={() => { setTaskDefaultEdit(null); resetTdForm(); }}
        title={taskDefaultEdit ? `Edit Task Default: ${taskDefaultEdit.task_type}` : "Add Task Default"}
      >
        <form className={styles.form} onSubmit={(e) => { e.preventDefault(); handleSaveTaskDefault(); }} noValidate>
          {!taskDefaultEdit && (
            <div className={styles.field}>
              <label className={styles.label} htmlFor="td-task-type">Task Type</label>
              <select id="td-task-type" className={styles.select} value={tdTaskType} onChange={(e) => setTdTaskType(e.target.value)}>
                {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          )}
          {taskDefaultEdit && (
            <p className={styles.mutedMeta}>Task type: <Badge variant="tag">{taskDefaultEdit.task_type}</Badge></p>
          )}
          <div className={styles.field}>
            <label className={styles.label} htmlFor="td-provider">Provider</label>
            <select id="td-provider" className={styles.select} value={tdProviderId} onChange={(e) => setTdProviderId(e.target.value)}>
              <option value="">— Select provider —</option>
              {providers.filter((p) => p.enabled).map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.provider_type})</option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="td-descriptor">Model Descriptor (optional)</label>
            <select id="td-descriptor" className={styles.select} value={tdDescriptorId} onChange={(e) => setTdDescriptorId(e.target.value)}>
              <option value="">— None (let provider decide) —</option>
              {descriptors.filter((d) => d.enabled).map((d) => (
                <option key={d.id} value={d.id}>{d.model_name}{d.display_name ? ` (${d.display_name})` : ""}</option>
              ))}
            </select>
          </div>
          {tdError && <p className={styles.formError} role="alert">{tdError}</p>}
          <div className={styles.dialogActions}>
            <Button type="submit" loading={tdMutation.isPending}>Save Task Default</Button>
            <Button type="button" variant="secondary" onClick={() => { setTaskDefaultEdit(null); resetTdForm(); }}>Cancel</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
