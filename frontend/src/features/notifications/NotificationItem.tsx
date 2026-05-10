import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { markRead, type Notification } from "@/api/notifications";
import { Badge } from "@/components/primitives/Badge";
import styles from "./NotificationsPage.module.css";

interface NotificationItemProps {
  notification: Notification;
}

export function NotificationItem({ notification }: NotificationItemProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const read = useMutation({
    mutationFn: () => markRead(notification.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-unread"] });
    },
  });

  function openNotification() {
    if (!notification.read) read.mutate();
    void navigate({ to: "/doc/$docId", params: { docId: notification.doc_id } });
  }

  return (
    <button className={`${styles.row} ${!notification.read ? styles.rowUnread : ""}`} onClick={openNotification}>
      <div className={styles.rowMain}>
        <span className={styles.docTitle}>{notification.doc_title || "Accessible document"}</span>
        <span className={styles.subInfo}>Matched <em>{notification.subscription_name}</em> · {Math.round(notification.similarity * 100)}% evidence match</span>
      </div>
      <div className={styles.rowMeta}>{!notification.read && <Badge variant="warning">New</Badge>}<span className={styles.date}>{new Date(notification.created_at).toLocaleDateString()}</span></div>
    </button>
  );
}
