import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { SheetManifestPreview } from "./SheetManifestPreview";
import type { PreviewManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  usePreviewManifest: vi.fn(),
}));

vi.mock("./SheetViewer", () => ({
  SheetViewer: () => <div data-testid="sheet-viewer" />,
}));

const mockedHook = vi.mocked(previewApi.usePreviewManifest);

function manifest(over: Partial<PreviewManifest>): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind: "office_sheets",
    renderer: "sheet_grid",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: {
      unit: "sheet",
      count: 1,
      items: [{ index: 0, label: "S", artifact_id: "sheet-0" }],
    },
    artifacts: [],
    email: null,
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "body", regions_available: false },
    ...over,
  };
}

function hookResult(over: Partial<ReturnType<typeof previewApi.usePreviewManifest>>) {
  return { data: undefined, isLoading: false, isError: false, ...over } as ReturnType<
    typeof previewApi.usePreviewManifest
  >;
}

beforeEach(() => mockedHook.mockReset());

describe("SheetManifestPreview dispatch", () => {
  const props = { docId: "doc-1", fallback: <div data-testid="fallback" /> };

  it("renders the SheetViewer when ready", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "ready" }) }));
    render(<SheetManifestPreview {...props} />);
    expect(screen.getByTestId("sheet-viewer")).toBeInTheDocument();
  });

  it("shows a preparing state while pending", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "pending" }) }));
    render(<SheetManifestPreview {...props} />);
    expect(screen.getByText("Preparing preview…")).toBeInTheDocument();
  });

  it("falls back when the render failed", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ status: "failed" }) }));
    render(<SheetManifestPreview {...props} />);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
  });

  it("falls back when the renderer is not sheet_grid", () => {
    mockedHook.mockReturnValue(hookResult({ data: manifest({ renderer: "text" }) }));
    render(<SheetManifestPreview {...props} />);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
  });
});
