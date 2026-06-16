import { useNavigate } from "@tanstack/react-router";
import {
  ServerIcon,
  Users,
  UserCircle,
  Activity,
  Cpu,
  ShieldQuestion,
  FlaskConical,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import styles from "./AdminHubPage.module.css";

export function AdminHubPage() {
  const navigate = useNavigate();
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Admin</h1>
      <p className={styles.subtitle}>
        Manage sources, users, groups, and system settings.
      </p>
      <div className={styles.grid}>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/users" })}
        >
          <UserCircle size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Users</span>
          <span className={styles.cardDesc}>
            View and manage users, roles, and group memberships
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/sources" })}
        >
          <ServerIcon size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Sources</span>
          <span className={styles.cardDesc}>
            Manage ingestion sources, sync, and permissions
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/groups" })}
        >
          <Users size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Groups</span>
          <span className={styles.cardDesc}>
            Manage user groups, memberships, and hierarchy
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/ingestion" })}
        >
          <Activity size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Ingestion</span>
          <span className={styles.cardDesc}>
            Monitor pipeline job status and per-document traces
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/model-providers" })}
        >
          <Cpu size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Model Providers</span>
          <span className={styles.cardDesc}>
            Manage LLM providers, model descriptors, and task defaults
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/ldap" })}
        >
          <ShieldQuestion size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>LDAP Mappings</span>
          <span className={styles.cardDesc}>
            Search LDAP groups and map them to Tomorrowland groups
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/permission-simulator" })}
        >
          <ShieldCheck size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Permission Simulator</span>
          <span className={styles.cardDesc}>
            Simulate user/group access and diagnose allow/deny reasoning
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/config" })}
        >
          <SlidersHorizontal size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Runtime Configuration</span>
          <span className={styles.cardDesc}>
            Inspect and override environment-backed settings safely
          </span>
        </button>
        <button
          type="button"
          className={styles.card}
          onClick={() => navigate({ to: "/admin/quality-lab" })}
        >
          <FlaskConical size={32} className={styles.cardIcon} />
          <span className={styles.cardTitle}>Quality Lab</span>
          <span className={styles.cardDesc}>
            Upload eval results and track retrieval quality trends
          </span>
        </button>
      </div>
    </div>
  );
}
