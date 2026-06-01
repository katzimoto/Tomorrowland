import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, X, Pencil, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { Dialog } from "@/components/primitives/Dialog";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import type { SourceDocument } from "@/api/admin";
import styles from "./AdminSourcesPage.module.css";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

const _JOB_LABELS: Record<string, string> = {
  process_document: "Parse",
  vector_index_document: "Vector",
  intelligence_document: "Intel",
  alert_document: "Alert",
  enrich_document: "Enrich",
  translate_document: "Translate",
  index_document: "Index",
};

function jobLabel(jobType: string) {
  return _JOB_LABELS[jobType] || jobType;
}

const _PIPELINE_ORDER: Record<string, number> = {
  process_document: 1,
  translate_document: 2,
  index_document: 3,
  vector_index_document: 4,
  intelligence_document: 5,
  alert_document: 6,
  enrich_document: 7,
};

function jobStep(jobType: string) {
  return _PIPELINE_ORDER[jobType] ?? 99;
}

function jobBadge(status: string) {
  if (status === "succeeded") return "success";
  if (status === "running") return "warning";
  if (status === "pending" || status === "retry") return "neutral";
  if (status === "dead_letter") return "danger";
  return "neutral";
}

function durationMs(start: string | null, end: string | null): string | null {
  if (!start) return null;
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const ms = e - s;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60_000)}m`;
}

function SourceDocumentsSection({ sourceId }: { sourceId: string }) {
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [, setTick] = useState(0);
  const tickRef = useRef<ReturnType<typeof setInterval>>(null);

  useEffect(() => {
    tickRef.current = setInterval(() => setTick((t) => t + 1), 1000);
    return () => { if (tickRef.current) clearInterval(tickRef.current); };
  }, []);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["source-documents", sourceId],
    queryFn: () => adminApi.getSourceDocuments(sourceId),
    refetchInterval: 10_000,
  });

  const toggle = (docId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const handleRequeue = async (documentId: string) => {
    try {
      const res = await adminApi.requeueDocument(documentId);
      showToast("success", `${res.requeued} job(s) requeued.`);
      qc.invalidateQueries({ queryKey: ["source-documents", sourceId] });
    } catch {
      showToast("error", "Failed to requeue jobs.");
    }
  };

  const handleDelete = async (documentId: string) => {
    try {
      await adminApi.deleteDocument(documentId);
      showToast("success", "Document deleted.");
      qc.invalidateQueries({ queryKey: ["source-documents", sourceId] });
    } catch {
      showToast("error", "Failed to delete document.");
    }
  };

  if (isLoading) return <div className={styles.section}><SkeletonRow count={4} /></div>;
  if (isError) return <div className={styles.section}><EmptyState title="Failed to load documents" body="Could not retrieve source documents." /></div>;

  const docs = data?.documents ?? [];
  if (docs.length === 0) {
    return (
      <div className={styles.section}>
        <h2>Documents</h2>
        <p className={styles.mutedMeta}>No documents yet. Sync the source to ingest documents.</p>
      </div>
    );
  }

  return (
    <div className={styles.section}>
      <h2>Documents ({data?.total ?? docs.length})</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th style={{ width: "42%" }}>Title</th>
              <th style={{ width: "8%" }}>Type</th>
              <th style={{ width: "6%" }}>Lang</th>
              <th style={{ width: "18%" }}>Progress</th>
              <th>State</th>
              <th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                expanded={expanded.has(doc.id)}
                onToggle={() => toggle(doc.id)}
                onRequeue={() => handleRequeue(doc.id)}
                onDelete={() => handleDelete(doc.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const _STAGE_ORDER: Record<string, number> = {
  pending: 0,
  parsed: 1,
  translated: 2,
  embedded: 3,
  indexed: 4,
};

function pipelineProgress(doc: SourceDocument): {
  pct: number;
  stage: string;
  isDone: boolean;
  hasFailed: boolean;
} {
  const processJob = doc.jobs.find((j) => j.job_type === "process_document");
  if (!processJob) {
    const total = doc.total_jobs;
    const succeeded = doc.succeeded_jobs;
    return {
      pct: total > 0 ? Math.round((succeeded / total) * 100) : 0,
      stage: doc.status,
      isDone: total > 0 && succeeded === total,
      hasFailed: doc.failed_jobs > 0,
    };
  }
  if (processJob.status === "succeeded" || processJob.status === "dead_letter") {
    const isDone = processJob.status === "succeeded";
    return {
      pct: isDone ? 100 : 0,
      stage: processJob.stage || processJob.status,
      isDone,
      hasFailed: !isDone,
    };
  }
  const stageIdx = _STAGE_ORDER[processJob.stage ?? ""] ?? 0;
  const totalStages = Object.keys(_STAGE_ORDER).length;
  return {
    pct: Math.round((stageIdx / totalStages) * 100),
    stage: processJob.stage || "pending",
    isDone: false,
    hasFailed: false,
  };
}

interface _PipelineStageRow {
  step: number;
  label: string;
  status: string;
  badge: "success" | "warning" | "neutral" | "danger";
  detail: string | null;
  rabbitMessageId: string | null;
  error: string | null;
}

function _pipelineStages(doc: SourceDocument): _PipelineStageRow[] {
  const processJob = doc.jobs.find((j) => j.job_type === "process_document");
  if (!processJob) return [];

  const currentStage = processJob.stage ?? "";
  const currentIdx = _STAGE_ORDER[currentStage] ?? 0;
  const stages: _PipelineStageRow[] = [];

  const stageDefs: { label: string; key: string }[] = [
    { key: "parsed", label: "Parse" },
    { key: "translated", label: "Translate" },
    { key: "embedded", label: "Embed" },
    { key: "indexed", label: "Index" },
  ];

  stageDefs.forEach((sd, idx) => {
    const stageIdx = _STAGE_ORDER[sd.key] ?? 0;
    const isPast = stageIdx < currentIdx;
    const isCurrent = stageIdx === currentIdx;
    const isFailed =
      processJob.status === "dead_letter" && isCurrent;

    stages.push({
      step: idx + 1,
      label: sd.label,
      status: isFailed
        ? "failed"
        : isPast
          ? "done"
          : isCurrent
            ? "processing"
            : "waiting",
      badge: isFailed
        ? "danger"
        : isPast || processJob.status === "succeeded"
          ? "success"
          : isCurrent
            ? "warning"
            : "neutral",
      detail: isCurrent ? processJob.stage : null,
      rabbitMessageId: isPast || (isCurrent && processJob.rabbit_message_id)
        ? processJob.rabbit_message_id || "\u2713"
        : null,
      error: isFailed ? processJob.last_error : null,
    });
  });

  return stages;
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    pending: "Pending",
    parsed: "Parsed",
    translated: "Translated",
    embedded: "Embedded",
    indexed: "Indexed",
  };
  return labels[stage] || stage;
}

function DocumentRow({
  doc,
  expanded,
  onToggle,
  onRequeue,
  onDelete,
}: {
  doc: SourceDocument;
  expanded: boolean;
  onToggle: () => void;
  onRequeue: () => void;
  onDelete: () => void;
}) {
  const progress = pipelineProgress(doc);
  const pct = progress.pct;
  const isDone = progress.isDone;
  const hasFailed = progress.hasFailed;
  const hasPending = !isDone && !hasFailed;

  const barColor = hasFailed
    ? "var(--color-danger)"
    : isDone
      ? "var(--color-success)"
      : "var(--color-warning)";

  return (
    <>
      <tr
        className={styles.nameCell}
        style={{ cursor: "pointer" }}
        onClick={onToggle}
      >
        <td>
          <a
            onClick={(e) => {
              e.stopPropagation();
              window.open(`/doc/${doc.id}`, "_blank", "noopener,noreferrer");
            }}
          >
            {doc.title || doc.external_id || doc.id.slice(0, 8)}
          </a>
        </td>
        <td>
          <Badge variant="neutral">{doc.mime_type?.split("/")[1] || doc.mime_type}</Badge>
        </td>
        <td>{doc.source_language?.toUpperCase() || "—"}</td>
        <td>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              flex: 1, height: 8, background: "var(--color-border)",
              borderRadius: 4, overflow: "hidden",
            }}>
              <div style={{
                width: `${pct}%`, height: "100%",
                background: barColor, borderRadius: 4,
                transition: "width 0.3s",
              }} />
            </div>
            <span style={{ fontSize: 12, color: "var(--color-text-secondary)", minWidth: 32 }}>
              {doc.total_jobs > 0 ? `${pct}%` : "—"}
            </span>
          </div>
        </td>
        <td>
          <Badge variant={hasFailed ? "danger" : isDone ? "success" : hasPending ? "warning" : "neutral"}>
            {isDone ? "Complete" : hasFailed ? "Failed" : stageLabel(progress.stage)}
          </Badge>
          <Button size="sm" variant="secondary" title="Requeue failed jobs" onClick={(e) => { e.stopPropagation(); onRequeue(); }}>
            Rerun
          </Button>
          <Button size="sm" variant="secondary" title="Delete document" onClick={(e) => { e.stopPropagation(); onDelete(); }}>
            <Trash2 size={12} />
          </Button>
        </td>
        <td>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} style={{ padding: "0 16px 12px" }}>
            <div className={styles.tableWrap} style={{ margin: 0 }}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th style={{ width: 30 }}>#</th>
                    <th style={{ width: "10%" }}>Stage</th>
                    <th style={{ width: "10%" }}>Status</th>
                    <th style={{ width: 48 }}>Try</th>
                    <th style={{ width: "10%" }}>Phase</th>
                    <th style={{ width: 64 }}>Duration</th>
                    <th style={{ width: 80 }}>RabbitMQ</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.jobs.length === 0 ? (
                    <tr>
                      <td colSpan={8} className={styles.mutedMeta}>
                        No pipeline jobs yet.
                      </td>
                    </tr>
                  ) : doc.jobs.some((j) => j.job_type === "process_document") ? (
                    _pipelineStages(doc).map((s) => (
                      <tr key={s.label}>
                        <td style={{ color: "var(--color-text-secondary)", fontSize: 12 }}>
                          {s.step}
                        </td>
                        <td>{s.label}</td>
                        <td>
                          {s.status === "waiting" ? (
                            <span style={{ color: "var(--color-text-secondary)", fontSize: 12 }}>—</span>
                          ) : (
                            <Badge variant={s.badge}>{s.status}</Badge>
                          )}
                        </td>
                        <td style={{ textAlign: "center" }} colSpan={3}>
                          {s.detail || "—"}
                        </td>
                        <td style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                          {s.rabbitMessageId ? "\u2713" : "—"}
                        </td>
                        <td className={styles.error} style={{ fontSize: 12, maxWidth: 280 }}>
                          {s.error || "—"}
                        </td>
                      </tr>
                    ))
                  ) : (
                    [...doc.jobs]
                      .sort((a, b) => jobStep(a.job_type) - jobStep(b.job_type))
                      .map((job) => (
                        <tr key={job.id}>
                          <td style={{ color: "var(--color-text-secondary)", fontSize: 12 }}>
                            {jobStep(job.job_type)}
                          </td>
                          <td>{jobLabel(job.job_type)}</td>
                          <td>
                            <Badge variant={jobBadge(job.status)}>{job.status}</Badge>
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {job.attempts}/{job.max_attempts}
                          </td>
                          <td style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                            {job.stage || "—"}
                          </td>
                          <td style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                            {durationMs(job.created_at, job.status === "succeeded" || job.status === "dead_letter" ? job.updated_at : null) || "—"}
                          </td>
                          <td style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                            {job.rabbit_message_id ? "\u2713" : "—"}
                          </td>
                          <td className={styles.error} style={{ fontSize: 12, maxWidth: 280 }}>
                            {job.last_error || "—"}
                          </td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function AdminSourceDetailPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const { sourceId } = useParams({ from: "/app/admin/sources/$sourceId" });
  const [addingGroup, setAddingGroup] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editLang, setEditLang] = useState("");

  const { data: source, isLoading, isError } = useQuery({
    queryKey: ["admin-source", sourceId],
    queryFn: () => adminApi.getSource(sourceId!),
    enabled: !!sourceId,
  });

  const { data: allGroups } = useQuery({
    queryKey: ["admin-groups"],
    queryFn: () => adminApi.listGroups(),
  });

  const grantMutation = useMutation({
    mutationFn: (groupId: string) => adminApi.grantPermission(sourceId!, groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-source", sourceId] });
      setAddingGroup(false);
      showToast("success", "Group granted access.");
    },
    onError: () => {
      showToast("error", "Failed to grant access.");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (groupId: string) => adminApi.revokePermission(sourceId!, groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-source", sourceId] });
      showToast("success", "Group access revoked.");
    },
    onError: () => {
      showToast("error", "Failed to revoke access.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => adminApi.updateSource(sourceId!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-source", sourceId] });
      setIsEditing(false);
      showToast("success", "Source updated.");
    },
    onError: () => {
      showToast("error", "Failed to update source.");
    },
  });

  const deleteSourceMutation = useMutation({
    mutationFn: () => adminApi.deleteSource(sourceId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      showToast("success", "Source deleted.");
      navigate({ to: "/admin/sources" });
    },
    onError: () => {
      showToast("error", "Failed to delete source.");
    },
  });

  if (isLoading) {
    return (
      <div className={styles.page}>
        <SkeletonRow count={8} />
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

  const availableGroups = (allGroups || []).filter(
    (g) => !source.groups.some((sg) => sg.id === g.id),
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin/sources" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>{source.name}</h1>
        <Badge variant={source.enabled ? "success" : "neutral"}>
          {source.enabled ? "Enabled" : "Disabled"}
        </Badge>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin/sources/$sourceId/edit", params: { sourceId: sourceId! } })}>
          <Pencil size={14} />
          Edit Source
        </Button>
        <Button variant="secondary" size="sm" onClick={() => { if (confirm("Delete this source and all its documents?")) deleteSourceMutation.mutate(); }}>
          <Trash2 size={14} />
          Delete
        </Button>
      </div>

      <div className={styles.section}>
        <h2>Configuration</h2>
        <dl className={styles.dl}>
          <dt>Type</dt>
          <dd>{source.type}</dd>
          <dt>Path</dt>
          <dd>{source.path || "—"}</dd>
          <dt>Language</dt>
          <dd>{source.source_language || "—"}</dd>
          <dt>Schedule</dt>
          <dd>{source.schedule || "Manual only"}</dd>
          {Object.entries(source.config).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd><code>{String(value)}</code></dd>
            </div>
          ))}
        </dl>
      </div>

      <div className={styles.section}>
        <h2>Sync Status</h2>
        {source.last_sync_status ? (
          <dl className={styles.dl}>
            <dt>Status</dt>
            <dd>
              <Badge variant={source.last_sync_status === "failed" ? "danger" : "success"}>
                {source.last_sync_status}
              </Badge>
            </dd>
            <dt>Indexed</dt>
            <dd>{source.last_sync_indexed ?? 0}</dd>
            <dt>Skipped</dt>
            <dd>{source.last_sync_skipped ?? 0}</dd>
            <dt>Failed</dt>
            <dd>{source.last_sync_failed ?? 0}</dd>
            {source.last_sync_at && <dt>Last run</dt>}
            {source.last_sync_at && <dd>{formatDateTime(source.last_sync_at)}</dd>}
            {source.last_sync_error && <dt>Error</dt>}
            {source.last_sync_error && <dd className={styles.error}>{source.last_sync_error}</dd>}
          </dl>
        ) : (
          <p className={styles.mutedMeta}>Never synced</p>
        )}
      </div>

      <div className={styles.section}>
        <h2>Validation</h2>
        {source.last_validation_status ? (
          <dl className={styles.dl}>
            <dt>Status</dt>
            <dd>
              <Badge variant={source.last_validation_status === "ok" ? "success" : "danger"}>
                {source.last_validation_status}
              </Badge>
            </dd>
            {source.last_validated_at && <dt>Last checked</dt>}
            {source.last_validated_at && <dd>{formatDateTime(source.last_validated_at)}</dd>}
            {source.last_validation_error && <dt>Error</dt>}
            {source.last_validation_error && (
              <dd className={styles.error}>{source.last_validation_error}</dd>
            )}
          </dl>
        ) : (
          <p className={styles.mutedMeta}>Not yet validated</p>
        )}
      </div>

      <div className={styles.section}>
        <h2>Permissions</h2>
        <p className={styles.mutedMeta}>
          Groups listed here can search and open documents from this source.
        </p>

        {source.groups.length > 0 ? (
          <>
            <ul className={styles.groupList}>
              {source.groups.map((g) => (
                <li key={g.id} className={styles.groupItem}>
                  <Badge variant="neutral">{g.name}</Badge>
                  <button
                    className={styles.removeBtn}
                    type="button"
                    aria-label={`Remove ${g.name}`}
                    onClick={() => revokeMutation.mutate(g.id)}
                    disabled={revokeMutation.isPending}
                  >
                    <X size={12} />
                  </button>
                </li>
              ))}
            </ul>
            {source.groups.length === 1 && (
              <p className={styles.warning}>
                Removing this group will leave the source with no user access.
                Existing indexed documents remain, but regular users will not
                be able to search this source.
              </p>
            )}
          </>
        ) : (
          <p className={styles.mutedMeta}>
            No groups have access yet. Documents can sync, but regular users
            cannot search this source.
          </p>
        )}

        {addingGroup ? (
          <div className={styles.addGroupRow}>
            <select
              className={styles.select}
              aria-label="Select group"
              onChange={(e) => {
                if (e.target.value) {
                  grantMutation.mutate(e.target.value);
                }
              }}
              value=""
            >
              <option value="" disabled>
                Select a group…
              </option>
              {availableGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={() => setAddingGroup(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setAddingGroup(true)}
            disabled={availableGroups.length === 0}
          >
            <Plus size={14} />
            Add group access
          </Button>
        )}
      </div>

      <SourceDocumentsSection sourceId={sourceId!} />

      <Dialog
        open={isEditing}
        onClose={() => setIsEditing(false)}
        title={`Edit: ${source.name}`}
      >
        <div className={styles.form}>
          <label className={styles.label}>
            Name
            <input
              className={styles.input}
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </label>
          <label className={styles.label}>
            Language
            <select
              className={styles.select}
              value={editLang}
              onChange={(e) => setEditLang(e.target.value)}
            >
              <option value="en">English</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="es">Spanish</option>
              <option value="ar">Arabic</option>
              <option value="zh">Chinese</option>
              <option value="he">Hebrew</option>
            </select>
          </label>
          <label className={styles.label}>
            <input
              type="checkbox"
              checked={source.enabled}
              onChange={(e) => {
                updateMutation.mutate({ enabled: e.target.checked });
              }}
            />{" "}
            Enabled
          </label>
          <div className={styles.dialogActions}>
            <Button
              onClick={() => {
                const payload: Record<string, unknown> = {};
                if (editName !== source.name) payload.name = editName;
                if (editLang !== (source.source_language || "")) payload.source_language = editLang;
                updateMutation.mutate(payload);
              }}
              loading={updateMutation.isPending}
            >
              Save
            </Button>
            <Button variant="secondary" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
