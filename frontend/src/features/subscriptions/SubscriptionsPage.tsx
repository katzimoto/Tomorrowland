import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { createSubscription, deleteSubscription, listSubscriptions, updateSubscription, type Subscription, type SubscriptionWrite } from "@/api/subscriptions";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { SavedSearchToSubscription } from "./SavedSearchToSubscription";
import { SubscriptionForm } from "./SubscriptionForm";
import styles from "./SubscriptionsPage.module.css";

const DEFAULT_FORM: SubscriptionWrite = { name: "", query: "", similarity_threshold: 0.75, enabled: true };

export function SubscriptionsPage() {
  const t = useT();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [defaults, setDefaults] = useState<SubscriptionWrite>(DEFAULT_FORM);
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();
  const { data = [], isLoading, isError } = useQuery({ queryKey: ["subscriptions"], queryFn: listSubscriptions, staleTime: 2 * 60_000 });
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
  const save = useMutation({
    mutationFn: (values: SubscriptionWrite) => editing ? updateSubscription(editing.id, values) : createSubscription(values),
    onSuccess: () => { setDialogOpen(false); setEditing(null); setDefaults(DEFAULT_FORM); invalidate(); },
    onError: () => showToast("error", t.subscriptions.saveError),
  });
  const remove = useMutation({
    mutationFn: deleteSubscription,
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ["subscriptions"] });
      const previous = queryClient.getQueryData<Subscription[]>(["subscriptions"]);
      queryClient.setQueryData<Subscription[]>(["subscriptions"], (current = []) =>
        current.filter((sub) => sub.id !== id),
      );
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(["subscriptions"], context.previous);
      showToast("error", t.subscriptions.deleteError);
    },
    onSettled: invalidate,
  });
  const toggle = useMutation({
    mutationFn: (sub: Subscription) => updateSubscription(sub.id, { name: sub.name, query: sub.query, similarity_threshold: sub.similarity_threshold, enabled: !sub.enabled }),
    onMutate: async (sub) => {
      await queryClient.cancelQueries({ queryKey: ["subscriptions"] });
      const previous = queryClient.getQueryData<Subscription[]>(["subscriptions"]);
      queryClient.setQueryData<Subscription[]>(["subscriptions"], (current = []) =>
        current.map((item) => item.id === sub.id ? { ...item, enabled: !item.enabled } : item),
      );
      return { previous };
    },
    onError: (_error, _sub, context) => {
      if (context?.previous) queryClient.setQueryData(["subscriptions"], context.previous);
      showToast("error", t.subscriptions.saveError);
    },
    onSettled: invalidate,
  });

  function openCreate(values: SubscriptionWrite = DEFAULT_FORM) { setEditing(null); setDefaults(values); setDialogOpen(true); }
  function openEdit(sub: Subscription) { setEditing(sub); setDefaults({ name: sub.name, query: sub.query, similarity_threshold: sub.similarity_threshold, enabled: sub.enabled }); setDialogOpen(true); }

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>{t.subscriptions.title}</h1><Button size="sm" onClick={() => openCreate()}><Plus size={14} /> {t.subscriptions.newBtn}</Button></header>
      <div className={styles.body}>
        <SavedSearchToSubscription onSelect={openCreate} />
        <section className={styles.subscriptionBox} aria-labelledby="subscriptions-title">
          <div className={styles.sectionHeader}><h2 id="subscriptions-title">{t.subscriptions.active}</h2><Badge variant="source">{t.subscriptions.notifBadge}</Badge></div>
          {isLoading && <p className={styles.muted}>{t.subscriptions.loading}</p>}
          {isError && <EmptyState title={t.subscriptions.failedTitle} body={t.subscriptions.failedBody} />}
          {!isLoading && !isError && data.length === 0 && <EmptyState title={t.subscriptions.emptyTitle} body={t.subscriptions.emptyBody} action={<Button onClick={() => openCreate()}>{t.subscriptions.createBtn}</Button>} />}
          {data.length > 0 && <ul className={styles.list}>{data.map((sub) => <li key={sub.id} className={styles.row}><div className={styles.rowMain}><button className={styles.rowName} onClick={() => openEdit(sub)}>{sub.name}</button><span className={styles.rowQuery}>{sub.query}</span></div><div className={styles.rowMeta}>{sub.unread_count > 0 && <Badge variant="warning">{t.subscriptions.newCount(sub.unread_count)}</Badge>}<Badge variant={sub.enabled ? "success" : "neutral"}>{sub.enabled ? t.subscriptions.statusActive : t.subscriptions.statusPaused}</Badge><button className={styles.toggleBtn} onClick={() => toggle.mutate(sub)}>{sub.enabled ? t.subscriptions.pause : t.subscriptions.resume}</button><button className={styles.deleteBtn} onClick={() => remove.mutate(sub.id)} aria-label={t.subscriptions.deleteLabel(sub.name)}><Trash2 size={14} /></button></div></li>)}</ul>}
        </section>
      </div>
      <Dialog open={dialogOpen} onClose={() => { setDialogOpen(false); setEditing(null); }} title={editing ? t.subscriptions.editTitle : t.subscriptions.newTitle}>
        <SubscriptionForm key={`${editing?.id ?? "new"}-${defaults.query}`} defaultValues={defaults} onSubmit={(values) => save.mutate(values)} onCancel={() => setDialogOpen(false)} loading={save.isPending} />
      </Dialog>
    </div>
  );
}
