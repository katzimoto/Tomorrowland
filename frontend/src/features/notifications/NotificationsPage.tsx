import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listNotifications, markRead } from "@/api/notifications";
import { Badge } from "@/components/primitives/Badge";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./NotificationsPage.module.css";

export function NotificationsPage() {
  const navigate = useNavigate();
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(false),
  });

  const readMut = useMutation({
    mutationFn: (id: string) => markRead(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: () => showToast("error", "Failed to mark notification as read."),
  });

  function handleClick(notificationId: string, docId: string, isRead: boolean) {
    if (!isRead) readMut.mutate(notificationId);
    void navigate({ to: "/doc/$docId", params: { docId } });
  }

  const notifications = data ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Notifications</h1>
      </header>

      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>Loading…</p>}
        {isError && <EmptyState title="Failed to load notifications" body="Could not reach the server." />}
        {!isLoading && !isError && notifications.length === 0 && (
          <EmptyState
            title="No notifications"
            body="You'll be notified here when documents match your subscriptions."
          />
        )}
        {notifications.length > 0 && (
          <ul className={styles.list}>
            {notifications.map((n) => (
              <li key={n.id}>
                <button
                  className={`${styles.row} ${!n.read ? styles.rowUnread : ""}`}
                  onClick={() => handleClick(n.id, n.doc_id, n.read)}
                >
                  <div className={styles.rowMain}>
                    <span className={styles.docTitle}>{n.doc_title || n.doc_id}</span>
                    <span className={styles.subInfo}>
                      Matched <em>{n.subscription_name}</em> · {Math.round(n.similarity * 100)}% match
                    </span>
                  </div>
                  <div className={styles.rowMeta}>
                    {!n.read && <Badge variant="warning">New</Badge>}
                    <span className={styles.date}>{new Date(n.created_at).toLocaleDateString()}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
