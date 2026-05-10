import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { ToastProvider } from "@/components/primitives/Toast";
import { LanguageProvider } from "@/i18n/LanguageProvider";
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
