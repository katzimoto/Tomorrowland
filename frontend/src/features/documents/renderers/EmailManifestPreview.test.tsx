import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { EmailManifestPreview } from "./EmailManifestPreview";
import type { PreviewManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: Record<string, unknown>) => (
    <a {...rest}>{children as React.ReactNode}</a>
  ),
}));

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  usePreviewManifest: vi.fn(),
  getPreviewArtifactText: vi.fn().mockResolvedValue(""),
}));

// EmailPreview (the fallback) fetches document text — stub it out.
vi.mock("@/api/documents", () => ({
  getDocumentText: vi.fn().mockResolvedValue({ text: "fallback body", truncated: false, offset: 0, limit: 10000, total_length: 13 }),
}));

const mockedHook = vi.mocked(previewApi.usePreviewManifest);

function manifest(status: PreviewManifest["status"], kind: PreviewManifest["kind"] = "email"): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind,
    renderer: "email",
    status,
    error: null,
    generated_at: null,
    retry_after_ms: status === "pending" ? 1500 : null,
    navigation: { unit: "none", count: 0, items: [] },
    artifacts: [],
    email: {
      subject: "Hi",
      from: "a@example.com",
      to: [],
      cc: [],
      bcc: [],
      date: null,
      message_id: null,
      in_reply_to: null,
      has_html_body: false,
      has_text_body: true,
      quoted_ranges: [],
      inline_images: [],
      skipped_inline_images: 0,
      blocked_remote_images: 0,
      embedded_inline_images: 0,
      attachments: [],
    },
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "body", regions_available: false },
  };
}

function hookResult(over: Partial<ReturnType<typeof previewApi.usePreviewManifest>>) {
  return { data: undefined, isLoading: false, isError: false, ...over } as ReturnType<
    typeof previewApi.usePreviewManifest
  >;
}

beforeEach(() => mockedHook.mockReset());

describe("EmailManifestPreview dispatch", () => {
  const props = { docId: "doc-1", fallbackText: "raw", metadata: { from: "a@example.com" } };

  it("renders the EmailViewer when the manifest is ready", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest("ready") }));
    render(<EmailManifestPreview {...props} />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
  });

  it("shows a preparing state while the render is pending", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest("pending") }));
    render(<EmailManifestPreview {...props} />);
    expect(screen.getByText("Preparing preview…")).toBeInTheDocument();
  });

  it("falls back to the legacy renderer when the render failed", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest("failed") }));
    render(<EmailManifestPreview {...props} />);
    // Fallback EmailPreview renders the metadata header, not the manifest viewer region.
    expect(screen.queryByRole("region", { name: "Email preview" })).not.toBeInTheDocument();
  });

  it("falls back when the manifest request errors", () => {
    mockedHook.mockReturnValue(hookResult({ isError: true }));
    render(<EmailManifestPreview {...props} />);
    expect(screen.queryByRole("region", { name: "Email preview" })).not.toBeInTheDocument();
  });
});
