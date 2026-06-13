import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { OfficeManifestPreview } from "./OfficeManifestPreview";
import type { PreviewManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  usePreviewManifest: vi.fn(),
}));

// PdfViewer pulls in pdfjs; stub it to a marker so we assert dispatch only.
vi.mock("./PdfViewer", () => ({
  PdfViewer: ({ src }: { src?: string }) => <div data-testid="pdf-viewer" data-src={src} />,
}));

const mockedHook = vi.mocked(previewApi.usePreviewManifest);

function manifest(over: Partial<PreviewManifest>): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind: "office_doc",
    renderer: "libreoffice_pdf",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: { unit: "page", count: 3, items: [] },
    artifacts: [],
    email: null,
    office: { pdf_artifact_id: "converted-pdf", page_count: 3, text_fallback: true },
    evidence: { supports_text_search: true, anchor_unit: "page", regions_available: false },
    ...over,
  };
}

function hookResult(over: Partial<ReturnType<typeof previewApi.usePreviewManifest>>) {
  return { data: undefined, isLoading: false, isError: false, ...over } as ReturnType<
    typeof previewApi.usePreviewManifest
  >;
}

beforeEach(() => mockedHook.mockReset());

describe("OfficeManifestPreview dispatch", () => {
  const fallback = <div data-testid="fallback" />;
  const props = { docId: "doc-1", fallback };

  it("renders the converted PDF when ready", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "ready" }) }));
    render(<OfficeManifestPreview {...props} />);
    const viewer = screen.getByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-src", "/api/preview/doc-1/artifact/converted-pdf");
  });

  it("shows a preparing state while pending", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "pending" }) }));
    render(<OfficeManifestPreview {...props} />);
    expect(screen.getByText("Preparing preview…")).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-viewer")).not.toBeInTheDocument();
  });

  it("falls back to extracted text when the render failed", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "failed" }) }));
    render(<OfficeManifestPreview {...props} />);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
  });

  it("falls back when the manifest request errors", () => {
    mockedHook.mockReturnValue(hookResult({ isError: true }));
    render(<OfficeManifestPreview {...props} />);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
  });

  it("falls back when the renderer is not libreoffice_pdf", () => {
    mockedHook.mockReturnValue(
      hookResult({ data: manifest({ renderer: "text", status: "ready" }) }),
    );
    render(<OfficeManifestPreview {...props} />);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
  });
});
