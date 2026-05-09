import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { listSubscriptions, createSubscription, updateSubscription, deleteSubscription, type Subscription, type SubscriptionWrite } from "@/api/subscriptions";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { TextInput } from "@/components/primitives/TextInput";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./SubscriptionsPage.module.css";

const DEFAULT_FORM: SubscriptionWrite = { name: "", query: "", similarity_threshold: 0.75, enabled: true };

export function SubscriptionsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [form, setForm] = useState<SubscriptionWrite>(DEFAULT_FORM);
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({ queryKey: ["subscriptions"], queryFn: listSubscriptions });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["subscriptions"] });

  const saveMut = useMutation({
    mutationFn: () => editing ? updateSubscription(editing.id, form) : createSubscription(form),
    onSuccess: () => { setDialogOpen(false); setEditing(null); setForm(DEFAULT_FORM); invalidate(); },
    onError: () => showToast("error", "Failed to save subscription."),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSubscription(id),
    onSuccess: invalidate,
    onError: () => showToast("error", "Failed to delete subscription."),
  });

  const toggleMut = useMutation({
    mutationFn: (sub: Subscription) => updateSubscription(sub.id, { ...sub, enabled: !sub.enabled }),
    onSuccess: invalidate,
    onError: () => showToast("error", "Failed to update subscription."),
  });

  function openCreate() { setEditing(null); setForm(DEFAULT_FORM); setDialogOpen(true); }
  function openEdit(sub: Subscription) {
    setEditing(sub);
    setForm({ name: sub.name, query: sub.query, similarity_threshold: sub.similarity_threshold, enabled: sub.enabled });
    setDialogOpen(true);
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Subscriptions</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus size={14} /> New subscription
        </Button>
      </header>

      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>Loading…</p>}
        {isError && <EmptyState title="Failed to load subscriptions" body="Could not reach the server." />}
        {!isLoading && !isError && (!data || data.length === 0) && (
          <EmptyState
            title="No subscriptions"
            body="Create a subscription to be notified when new documents match a query."
            action={<Button onClick={openCreate}>Create subscription</Button>}
          />
        )}
        {data && data.length > 0 && (
          <ul className={styles.list}>
            {data.map((sub) => (
              <li key={sub.id} className={styles.row}>
                <div className={styles.rowMain}>
                  <button className={styles.rowName} onClick={() => openEdit(sub)}>{sub.name}</button>
                  <span className={styles.rowQuery}>{sub.query}</span>
                </div>
                <div className={styles.rowMeta}>
                  {sub.unread_count > 0 && (
                    <Badge variant="warning">{sub.unread_count} new</Badge>
                  )}
                  <Badge variant={sub.enabled ? "success" : "neutral"}>
                    {sub.enabled ? "Active" : "Paused"}
                  </Badge>
                  <button
                    className={styles.toggleBtn}
                    onClick={() => toggleMut.mutate(sub)}
                    aria-label={sub.enabled ? "Pause subscription" : "Resume subscription"}
                  >
                    {sub.enabled ? "Pause" : "Resume"}
                  </button>
                  <button
                    className={styles.deleteBtn}
                    onClick={() => { if (window.confirm(`Delete subscription "${sub.name}"?`)) deleteMut.mutate(sub.id); }}
                    aria-label="Delete subscription"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Dialog
        open={dialogOpen}
        onClose={() => { setDialogOpen(false); setEditing(null); }}
        title={editing ? "Edit subscription" : "New subscription"}
      >
        <div className={styles.formFields}>
          <TextInput
            label="Name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="e.g. Vendor risk alerts"
          />
          <TextInput
            label="Query"
            value={form.query}
            onChange={(e) => setForm((f) => ({ ...f, query: e.target.value }))}
            placeholder="e.g. vendor risk assessment"
          />
          <label className={styles.sliderLabel}>
            Threshold: {Math.round(form.similarity_threshold * 100)}%
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={form.similarity_threshold}
              onChange={(e) => setForm((f) => ({ ...f, similarity_threshold: parseFloat(e.target.value) }))}
              className={styles.slider}
            />
          </label>
          <div className={styles.formActions}>
            <Button onClick={() => saveMut.mutate()} disabled={!form.name.trim() || !form.query.trim() || saveMut.isPending} loading={saveMut.isPending}>
              {editing ? "Save" : "Create"}
            </Button>
            <Button variant="secondary" onClick={() => { setDialogOpen(false); setEditing(null); }}>Cancel</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
