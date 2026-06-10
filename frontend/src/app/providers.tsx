import { useEffect, useRef, useState } from "react";
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

// Lives inside ToastProvider so it can reach useToast, while owning the
// QueryClient lifecycle. A ref keeps the show callback stable so the
// MutationCache onError closure never stales.
function InnerApp() {
  const { show } = useToast();
  const showRef = useRef(show);
  showRef.current = show;

  const [queryClient] = useState(
    () =>
      new QueryClient({
        mutationCache: new MutationCache({
          onError: (error) => {
            if (error instanceof ApiError && error.status >= 500) {
              showRef.current("error", "Server error — please try again");
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
      }),
  );

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
