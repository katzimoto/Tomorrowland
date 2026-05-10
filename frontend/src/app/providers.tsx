import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { ToastProvider } from "@/components/primitives/Toast";
import { LanguageProvider } from "@/i18n/LanguageProvider";
import {
  installPerformanceTelemetryDiagnostics,
  recordPerformanceEvent,
  startPerformanceTimer,
} from "@/lib/performanceTelemetry";
import { router } from "./routes";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export function Providers() {
  useEffect(() => {
    installPerformanceTelemetryDiagnostics();
    let finishRouteTimer: (() => number) | null = null;
    const unsubscribeStart = router.subscribe("onBeforeNavigate", (event) => {
      if (event.hrefChanged || event.pathChanged)
        finishRouteTimer = startPerformanceTimer();
    });
    const unsubscribeResolved = router.subscribe("onResolved", () => {
      if (!finishRouteTimer) return;
      recordPerformanceEvent("navigation.route", finishRouteTimer());
      finishRouteTimer = null;
    });
    return () => {
      unsubscribeStart();
      unsubscribeResolved();
    };
  }, []);

  return (
    <LanguageProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>
    </LanguageProvider>
  );
}
