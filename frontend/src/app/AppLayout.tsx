import { Outlet } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/primitives/Skeleton";
import styles from "./AppLayout.module.css";

export function AppLayout() {
  const { data: user, isLoading } = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
    staleTime: 5 * 60_000,
  });

  if (isLoading) {
    return (
      <div className={styles.loadingShell} aria-label="Loading application">
        <Skeleton width={72} height="100vh" />
        <div className={styles.loadingContent}>
          <Skeleton height={32} width="30%" />
          <Skeleton height={20} width="60%" />
          <Skeleton height={20} width="45%" />
        </div>
      </div>
    );
  }

  return (
    <AppShell isAdmin={user?.is_admin ?? false} unreadCount={0}>
      <Outlet />
    </AppShell>
  );
}
