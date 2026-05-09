import { NavRail } from "./NavRail";
import styles from "./AppShell.module.css";

interface AppShellProps {
  children: React.ReactNode;
  isAdmin?: boolean;
  unreadCount?: number;
}

export function AppShell({ children, isAdmin = false, unreadCount = 0 }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <NavRail isAdmin={isAdmin} unreadCount={unreadCount} />
      <main className={styles.main} id="main-content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
