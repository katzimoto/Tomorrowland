import styles from "./EmptyState.module.css";

interface EmptyStateProps {
  title: string;
  body?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

export function EmptyState({ title, body, action, icon }: EmptyStateProps) {
  return (
    <div className={styles.wrapper} role="status">
      {icon && <div className={styles.icon} aria-hidden>{icon}</div>}
      <p className={styles.title}>{title}</p>
      {body && <p className={styles.body}>{body}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
