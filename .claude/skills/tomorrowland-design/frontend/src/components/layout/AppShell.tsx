import { NavRail } from "./NavRail";
import styles from "./AppShell.module.css";

interface AppShellProps {
  children: React.ReactNode;
  isAdmin?: boolean;
  unreadCount?: number;
  userDisplayName?: string | null;
  userEmail?: string | null;
}

export function AppShell({ children, isAdmin = false, unreadCount = 0, userDisplayName = null, userEmail = null }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <NavRail isAdmin={isAdmin} unreadCount={unreadCount} userDisplayName={userDisplayName} userEmail={userEmail} />
      <main className={styles.main} id="main-content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
