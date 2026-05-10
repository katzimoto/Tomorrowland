import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { createSubscription, deleteSubscription, listSubscriptions, updateSubscription, type Subscription, type SubscriptionWrite } from "@/api/subscriptions";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { SavedSearchToSubscription } from "./SavedSearchToSubscription";
import { SubscriptionForm } from "./SubscriptionForm";
import styles from "./SubscriptionsPage.module.css";

const DEFAULT_FORM: SubscriptionWrite = { name: "", query: "", similarity_threshold: 0.75, enabled: true };

export function SubscriptionsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [defaults, setDefaults] = useState<SubscriptionWrite>(DEFAULT_FORM);
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();
  const { data = [], isLoading, isError } = useQuery({ queryKey: ["subscriptions"], queryFn: listSubscriptions });
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
  const save = useMutation({
    mutationFn: (values: SubscriptionWrite) => editing ? updateSubscription(editing.id, values) : createSubscription(values),
    onSuccess: () => { setDialogOpen(false); setEditing(null); setDefaults(DEFAULT_FORM); invalidate(); },
    onError: () => showToast("error", "Failed to save subscription."),
  });
  const remove = useMutation({ mutationFn: deleteSubscription, onSuccess: invalidate, onError: () => showToast("error", "Failed to delete subscription.") });
  const toggle = useMutation({ mutationFn: (sub: Subscription) => updateSubscription(sub.id, { name: sub.name, query: sub.query, similarity_threshold: sub.similarity_threshold, enabled: !sub.enabled }), onSuccess: invalidate });

  function openCreate(values: SubscriptionWrite = DEFAULT_FORM) { setEditing(null); setDefaults(values); setDialogOpen(true); }
  function openEdit(sub: Subscription) { setEditing(sub); setDefaults({ name: sub.name, query: sub.query, similarity_threshold: sub.similarity_threshold, enabled: sub.enabled }); setDialogOpen(true); }

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>Subscriptions</h1><Button size="sm" onClick={() => openCreate()}><Plus size={14} /> New subscription</Button></header>
      <div className={styles.body}>
        <SavedSearchToSubscription onSelect={openCreate} />
        <section className={styles.subscriptionBox} aria-labelledby="subscriptions-title">
          <div className={styles.sectionHeader}><h2 id="subscriptions-title">Active subscriptions</h2><Badge variant="source">Notifications</Badge></div>
          {isLoading && <p className={styles.muted}>Loading…</p>}
          {isError && <EmptyState title="Failed to load subscriptions" body="Could not reach the server." />}
          {!isLoading && !isError && data.length === 0 && <EmptyState title="No subscriptions" body="Create one from scratch or subscribe to a saved search." action={<Button onClick={() => openCreate()}>Create subscription</Button>} />}
          {data.length > 0 && <ul className={styles.list}>{data.map((sub) => <li key={sub.id} className={styles.row}><div className={styles.rowMain}><button className={styles.rowName} onClick={() => openEdit(sub)}>{sub.name}</button><span className={styles.rowQuery}>{sub.query}</span></div><div className={styles.rowMeta}>{sub.unread_count > 0 && <Badge variant="warning">{sub.unread_count} new</Badge>}<Badge variant={sub.enabled ? "success" : "neutral"}>{sub.enabled ? "Active" : "Paused"}</Badge><button className={styles.toggleBtn} onClick={() => toggle.mutate(sub)}>{sub.enabled ? "Pause" : "Resume"}</button><button className={styles.deleteBtn} onClick={() => remove.mutate(sub.id)} aria-label={`Delete ${sub.name}`}><Trash2 size={14} /></button></div></li>)}</ul>}
        </section>
      </div>
      <Dialog open={dialogOpen} onClose={() => { setDialogOpen(false); setEditing(null); }} title={editing ? "Edit subscription" : "New subscription"}>
        <SubscriptionForm key={`${editing?.id ?? "new"}-${defaults.query}`} defaultValues={defaults} onSubmit={(values) => save.mutate(values)} onCancel={() => setDialogOpen(false)} loading={save.isPending} />
      </Dialog>
    </div>
  );
}
