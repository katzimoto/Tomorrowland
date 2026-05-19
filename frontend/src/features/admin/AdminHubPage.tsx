import { useNavigate } from "@tanstack/react-router";
import { ServerIcon, Users } from "lucide-react";
import styles from "./AdminHubPage.module.css";

export function AdminHubPage() {
  const navigate = useNavigate();
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Admin</h1>
      <p className={styles.subtitle}>Manage sources, groups, and system settings.</p>
      <div className={styles.grid}>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/sources" })}
        >
          <ServerIcon size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Sources</span>
          <span className={styles.cardDesc}>Manage ingestion sources, sync, and permissions</span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/groups" })}
        >
          <Users size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Groups</span>
          <span className={styles.cardDesc}>Manage user groups, memberships, and hierarchy</span>
        </button>
      </div>
    </div>
  );
}
