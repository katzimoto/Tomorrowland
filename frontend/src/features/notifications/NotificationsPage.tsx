import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listNotifications } from "@/api/notifications";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useT } from "@/i18n/index";
import { NotificationItem } from "./NotificationItem";
import styles from "./NotificationsPage.module.css";

export function NotificationsPage() {
  const t = useT();
  const { data = [], isLoading, isError } = useQuery({ queryKey: ["notifications"], queryFn: () => listNotifications(false), staleTime: 60_000 });
  const unread = useMemo(() => data.filter((notification) => !notification.read), [data]);
  const read = useMemo(() => data.filter((notification) => notification.read), [data]);

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>{t.notifications.title}</h1></header>
      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>{t.notifications.loading}</p>}
        {isError && <EmptyState title={t.notifications.failedTitle} body={t.notifications.failedBody} />}
        {!isLoading && !isError && data.length === 0 && <EmptyState title={t.notifications.emptyTitle} body={t.notifications.emptyBody} />}
        {unread.length > 0 && <section aria-labelledby="unread-title"><h2 id="unread-title" className={styles.groupTitle}>{t.notifications.unread}</h2><ul className={styles.list}>{unread.map((notification) => <li key={notification.id}><NotificationItem notification={notification} /></li>)}</ul></section>}
        {read.length > 0 && <section aria-labelledby="read-title"><h2 id="read-title" className={styles.groupTitle}>{t.notifications.earlier}</h2><ul className={styles.list}>{read.map((notification) => <li key={notification.id}><NotificationItem notification={notification} /></li>)}</ul></section>}
      </div>
    </div>
  );
}
