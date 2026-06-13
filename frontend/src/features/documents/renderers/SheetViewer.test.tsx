import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { SheetViewer } from "./SheetViewer";
import type { PreviewManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  getPreviewArtifactText: vi.fn(),
}));

const mockedArtifact = vi.mocked(previewApi.getPreviewArtifactText);

function manifest(sheets: { index: number; label: string; artifact_id: string }[]): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind: "office_sheets",
    renderer: "sheet_grid",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: { unit: "sheet", count: sheets.length, items: sheets },
    artifacts: [],
    email: null,
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "body", regions_available: false },
  };
}

beforeEach(() => {
  mockedArtifact.mockReset();
  mockedArtifact.mockImplementation((_docId, artifactId) => {
    const grids: Record<string, unknown> = {
      "sheet-0": {
        name: "Budget",
        rows: [["Item", "Cost"], ["Rent", "1000"]],
        truncated: { rows: false, cols: false },
      },
      "sheet-1": {
        name: "Q2",
        rows: [["secret"]],
        truncated: { rows: true, cols: false },
      },
    };
    return Promise.resolve(JSON.stringify(grids[artifactId]));
  });
});

describe("SheetViewer", () => {
  const sheets = [
    { index: 0, label: "Budget", artifact_id: "sheet-0" },
    { index: 1, label: "Q2", artifact_id: "sheet-1" },
  ];

  it("renders the first sheet grid with tabs", async () => {
    render(<SheetViewer manifest={manifest(sheets)} docId="doc-1" />);
    expect(await screen.findByText("Rent")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Budget" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Q2" })).toBeInTheDocument();
  });

  it("switches sheets on tab click and shows a truncation note", async () => {
    render(<SheetViewer manifest={manifest(sheets)} docId="doc-1" />);
    await screen.findByText("Rent");
    fireEvent.click(screen.getByRole("tab", { name: "Q2" }));
    expect(await screen.findByText("secret")).toBeInTheDocument();
    expect(screen.getByRole("note")).toBeInTheDocument();
  });

  it("counts cell matches for the active sheet", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <SheetViewer
        manifest={manifest(sheets)}
        docId="doc-1"
        searchQuery="Rent"
        onMatchCountChange={onMatchCountChange}
      />,
    );
    await waitFor(() => expect(onMatchCountChange).toHaveBeenCalledWith(1));
  });
});
