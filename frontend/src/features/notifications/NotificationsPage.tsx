import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listNotifications, markRead } from "@/api/notifications";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useT } from "@/i18n/index";
import { NotificationItem } from "./NotificationItem";
import styles from "./NotificationsPage.module.css";

export function NotificationsPage() {
  const t = useT();
  const qc = useQueryClient();
  const { data = [], isLoading, isError } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(false),
    staleTime: 60_000,
  });
  const unread = useMemo(() => data.filter((n) => !n.read), [data]);
  const read = useMemo(() => data.filter((n) => n.read), [data]);

  const markAllMutation = useMutation({
    mutationFn: () => Promise.all(unread.map((n) => markRead(n.id))),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      void qc.invalidateQueries({ queryKey: ["notifications-unread"] });
    },
  });

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t.notifications.title}</h1>
        {unread.length > 0 && (
          <Button
            variant="secondary"
            size="sm"
            loading={markAllMutation.isPending}
            onClick={() => markAllMutation.mutate()}
          >
            Mark all as read
          </Button>
        )}
      </header>
      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>{t.notifications.loading}</p>}
        {isError && <EmptyState title={t.notifications.failedTitle} body={t.notifications.failedBody} />}
        {!isLoading && !isError && data.length === 0 && <EmptyState title={t.notifications.emptyTitle} body={t.notifications.emptyBody} />}
        {unread.length > 0 && (
          <section aria-labelledby="unread-title">
            <h2 id="unread-title" className={styles.groupTitle}>{t.notifications.unread}</h2>
            <ul className={styles.list}>
              {unread.map((n) => <li key={n.id}><NotificationItem notification={n} /></li>)}
            </ul>
          </section>
        )}
        {read.length > 0 && (
          <section aria-labelledby="read-title">
            <h2 id="read-title" className={styles.groupTitle}>{t.notifications.earlier}</h2>
            <ul className={styles.list}>
              {read.map((n) => <li key={n.id}><NotificationItem notification={n} /></li>)}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
