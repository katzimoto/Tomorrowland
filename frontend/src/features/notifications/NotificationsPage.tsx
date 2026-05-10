import { useQuery } from "@tanstack/react-query";
import { listNotifications } from "@/api/notifications";
import { EmptyState } from "@/components/primitives/EmptyState";
import { NotificationItem } from "./NotificationItem";
import styles from "./NotificationsPage.module.css";

export function NotificationsPage() {
  const { data = [], isLoading, isError } = useQuery({ queryKey: ["notifications"], queryFn: () => listNotifications(false) });
  const unread = data.filter((notification) => !notification.read);
  const read = data.filter((notification) => notification.read);

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>Notifications</h1></header>
      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>Loading…</p>}
        {isError && <EmptyState title="Failed to load notifications" body="Could not reach the server." />}
        {!isLoading && !isError && data.length === 0 && <EmptyState title="No notifications" body="You'll be notified here when documents match your subscriptions." />}
        {unread.length > 0 && <section aria-labelledby="unread-title"><h2 id="unread-title" className={styles.groupTitle}>Unread</h2><ul className={styles.list}>{unread.map((notification) => <li key={notification.id}><NotificationItem notification={notification} /></li>)}</ul></section>}
        {read.length > 0 && <section aria-labelledby="read-title"><h2 id="read-title" className={styles.groupTitle}>Earlier</h2><ul className={styles.list}>{read.map((notification) => <li key={notification.id}><NotificationItem notification={notification} /></li>)}</ul></section>}
      </div>
    </div>
  );
}
