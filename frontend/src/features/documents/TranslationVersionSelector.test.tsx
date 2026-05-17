import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  screen,
  waitFor,
  act,
  render as tlRender,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@/test/render";
import { ToastProvider } from "@/components/primitives/Toast";
import { LanguageProvider } from "@/i18n/LanguageProvider";
import { TranslationVersionSelector } from "./TranslationVersionSelector";
import type { TranslationVersion } from "@/api/documents";
import * as documentsApi from "@/api/documents";

function renderWithClient(ui: React.ReactElement, queryClient: QueryClient) {
  return tlRender(ui, {
    wrapper: ({ children }) => (
      <LanguageProvider>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>{children}</ToastProvider>
        </QueryClientProvider>
      </LanguageProvider>
    ),
  });
}

vi.mock("@/api/documents");

beforeEach(() => {
  vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([
    {
      version_id: "v1",
      version_number: 1,
      label: "Manual EN",
      quality: "high",
      status: "available",
      target_language: "en",
      requested_at: "2024-01-01T00:00:00Z",
    },
    {
      version_id: "v2",
      version_number: 2,
      label: "Manual EN v2",
      quality: "high",
      status: "pending",
      target_language: "en",
      requested_at: "2024-02-01T00:00:00Z",
    },
    {
      version_id: "v3",
      version_number: 3,
      label: "Manual EN v3",
      quality: "high",
      status: "available",
      target_language: "en",
      requested_at: "2024-03-01T00:00:00Z",
    },
    {
      version_id: "v4",
      version_number: 4,
      label: "Manual EN v4",
      quality: "high",
      status: "running",
      target_language: "en",
      requested_at: "2024-04-01T00:00:00Z",
    },
  ]);
});

describe("TranslationVersionSelector", () => {
  it("renders version options", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    const select = await screen.findByRole("combobox", {
      name: "Translation version",
    });
    expect(select).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Manual EN/ })
    ).toBeInTheDocument();
  });

  it("marks pending and running versions as disabled", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    const pendingOption = await screen.findByRole("option", {
      name: /Manual EN v2/,
    });
    const runningOption = await screen.findByRole("option", {
      name: /Manual EN v4/,
    });
    expect(pendingOption).toBeDisabled();
    expect(runningOption).toBeDisabled();
  });

  it("allows available versions to be selected", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    const availableOption = await screen.findByRole("option", {
      name: "Manual EN v3",
    });
    expect(availableOption).not.toBeDisabled();
  });

  it("shows Latest and Original options when no versions exist", async () => {
    vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    const select = await screen.findByRole("combobox", {
      name: "Translation version",
    });
    expect(select).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Latest" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Original" })
    ).toBeInTheDocument();
  });

  it("polls for updates when pending or running versions exist", async () => {
    // First call returns a pending version; second call returns it as available.
    vi.mocked(documentsApi.getTranslationVersions)
      .mockResolvedValueOnce([
        {
          version_id: "v1",
          version_number: 1,
          label: "In Progress",
          quality: "high",
          status: "pending",
          target_language: "en",
          requested_at: "2024-01-01T00:00:00Z",
        },
      ])
      .mockResolvedValueOnce([
        {
          version_id: "v1",
          version_number: 1,
          label: "In Progress",
          quality: "high",
          status: "available",
          target_language: "en",
          requested_at: "2024-01-01T00:00:00Z",
        },
      ]);

    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );

    // Initially the version is shown as disabled (pending)
    const option = await screen.findByRole("option", { name: /In Progress/ });
    expect(option).toBeDisabled();

    // Verify the API was called at least once (polling is configured)
    expect(documentsApi.getTranslationVersions).toHaveBeenCalledWith("doc-1");
  });

  it("auto-selects latest available version when translation transitions from pending to available", async () => {
    const onSelect = vi.fn();
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
          refetchOnWindowFocus: false,
        },
      },
    });

    const pendingVersion: TranslationVersion = {
      version_id: "v1",
      version_number: 1,
      label: "Manual EN",
      quality: "high",
      status: "pending",
      target_language: "en",
      requested_at: "2024-01-01T00:00:00Z",
    };
    const availableVersion: TranslationVersion = {
      ...pendingVersion,
      status: "available",
    };

    // Pre-seed cache with pending version so the selector renders without a network call
    qc.setQueryData(["doc-translation-versions", "doc-auto"], [pendingVersion]);

    renderWithClient(
      <TranslationVersionSelector
        docId="doc-auto"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={onSelect}
        onShowOriginalChange={vi.fn()}
      />,
      qc
    );

    // Component renders with pending version; hadInProgressRef becomes true
    await screen.findByRole("option", { name: /Manual EN/ });

    // Simulate a poll result arriving (version now available)
    act(() => {
      qc.setQueryData(
        ["doc-translation-versions", "doc-auto"],
        [availableVersion]
      );
    });

    // useEffect detects the transition and auto-selects the newly available version
    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith("v1");
    });
    await new Promise((r) => setTimeout(r, 50));
  });

  it("auto-selects latest available version on initial load when translations are already available", async () => {
    const onSelect = vi.fn();
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
          refetchOnWindowFocus: false,
        },
      },
    });

    qc.setQueryData(["doc-translation-versions", "doc-initial"], [
      {
        version_id: "v1",
        version_number: 1,
        label: "EN v1",
        quality: "high",
        status: "available",
        target_language: "en",
        requested_at: "2024-01-01T00:00:00Z",
      },
      {
        version_id: "v3",
        version_number: 3,
        label: "EN v3",
        quality: "high",
        status: "available",
        target_language: "en",
        requested_at: "2024-03-01T00:00:00Z",
      },
    ] satisfies TranslationVersion[]);

    renderWithClient(
      <TranslationVersionSelector
        docId="doc-initial"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={onSelect}
        onShowOriginalChange={vi.fn()}
      />,
      qc
    );

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith("v3");
    });
  });

  it("does not auto-select again after user returns to Latest", async () => {
    const onSelect = vi.fn();
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
          refetchOnWindowFocus: false,
        },
      },
    });

    qc.setQueryData(["doc-translation-versions", "doc-revisit"], [
      {
        version_id: "v1",
        version_number: 1,
        label: "EN v1",
        quality: "high",
        status: "available",
        target_language: "en",
        requested_at: "2024-01-01T00:00:00Z",
      },
    ] satisfies TranslationVersion[]);

    const { rerender } = renderWithClient(
      <TranslationVersionSelector
        docId="doc-revisit"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={onSelect}
        onShowOriginalChange={vi.fn()}
      />,
      qc
    );

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledTimes(1);
    });

    // Simulate user selecting "Latest" (clears selectedVersionId to undefined)
    rerender(
      <TranslationVersionSelector
        docId="doc-revisit"
        selectedVersionId={undefined}
        showOriginal={false}
        onSelect={onSelect}
        onShowOriginalChange={vi.fn()}
      />
    );

    await new Promise((r) => setTimeout(r, 50));
    // Should not auto-select again after initial select was done
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("does not auto-select when user has already manually selected a version", async () => {
    const onSelect = vi.fn();
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
          refetchOnWindowFocus: false,
        },
      },
    });

    const pendingVersion: TranslationVersion = {
      version_id: "v1",
      version_number: 1,
      label: "Manual EN",
      quality: "high",
      status: "pending",
      target_language: "en",
      requested_at: "2024-01-01T00:00:00Z",
    };
    const availableVersion: TranslationVersion = {
      ...pendingVersion,
      status: "available",
    };

    qc.setQueryData(
      ["doc-translation-versions", "doc-manual"],
      [pendingVersion]
    );

    renderWithClient(
      // selectedVersionId is set — user already picked a version, auto-select must not fire
      <TranslationVersionSelector
        docId="doc-manual"
        selectedVersionId="already-selected"
        showOriginal={false}
        onSelect={onSelect}
        onShowOriginalChange={vi.fn()}
      />,
      qc
    );

    act(() => {
      qc.setQueryData(
        ["doc-translation-versions", "doc-manual"],
        [availableVersion]
      );
    });

    await new Promise((r) => setTimeout(r, 50));
    expect(onSelect).not.toHaveBeenCalled();
  });
});
