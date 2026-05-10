import { useEffect } from "react";
import { Outlet } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { listNotifications } from "@/api/notifications";
import { AppShell } from "@/components/layout/AppShell";
import { CommandMenu } from "@/components/feedback/CommandMenu";
import { EmptyState } from "@/components/primitives/EmptyState";
import { Skeleton } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { finishNamedPerformanceTimer } from "@/lib/performanceTelemetry";
import styles from "./AppLayout.module.css";

export function AppLayout() {
  const t = useT();
  const {
    data: user,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
    staleTime: 5 * 60_000,
  });

  const { data: unreadNotifications } = useQuery({
    queryKey: ["notifications-unread"],
    queryFn: () => listNotifications(true),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (user && !isLoading && !isError) {
      finishNamedPerformanceTimer("login.shell", "login.shell");
    }
  }, [isError, isLoading, user]);

  if (isLoading) {
    return (
      <div className={styles.loadingShell} aria-label={t.app.loadingApp}>
        <Skeleton width={72} height="100vh" />
        <div className={styles.loadingContent}>
          <Skeleton height={32} width="30%" />
          <Skeleton height={20} width="60%" />
          <Skeleton height={20} width="45%" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={styles.loadingShell}>
        <EmptyState title={t.app.loadFailed} body={t.app.loadFailedBody} />
      </div>
    );
  }

  return (
    <AppShell
      isAdmin={user?.is_admin ?? false}
      unreadCount={unreadNotifications?.length ?? 0}
    >
      <CommandMenu />
      <Outlet />
    </AppShell>
  );
}
