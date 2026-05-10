import { render as tlRender, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactElement } from "react";
import { ToastProvider } from "@/components/primitives/Toast";
import { LanguageProvider } from "@/i18n/LanguageProvider";

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </LanguageProvider>
  );
}

export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return tlRender(ui, { wrapper: Wrapper, ...options });
}

export * from "@testing-library/react";
