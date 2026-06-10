import { useEffect, useState } from "react";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { ToastProvider } from "@/components/primitives/Toast";
import { useToast } from "@/components/primitives/ToastContext";
import { LanguageProvider } from "@/i18n/LanguageProvider";
import { ApiError } from "@/api/client";
import {
  installPerformanceTelemetryDiagnostics,
  recordPerformanceEvent,
  startPerformanceTimer,
} from "@/lib/performanceTelemetry";
import { router } from "./routes";

// Module-level so the MutationCache closure doesn't close over any React ref.
// InnerApp registers the live show callback via useEffect.
let _showError: ((type: "error", message: string) => void) | null = null;

const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status >= 500) {
        _showError?.("error", "Server error — please try again");
      }
    },
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

// Lives inside ToastProvider so it can reach useToast.
function InnerApp() {
  const { show } = useToast();

  useEffect(() => {
    _showError = show;
    return () => { _showError = null; };
  }, [show]);

  const [perfReady] = useState(() => {
    installPerformanceTelemetryDiagnostics();
    return true;
  });
  void perfReady;

  useEffect(() => {
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
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

export function Providers() {
  return (
    <LanguageProvider>
      <ToastProvider>
        <InnerApp />
      </ToastProvider>
    </LanguageProvider>
  );
}
