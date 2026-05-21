import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { PreviewPane } from "./PreviewPane";
import type { DocumentPreview } from "@/api/documents";

// Stub heavy renderers to keep PreviewPane dispatch tests fast
vi.mock("./renderers/PdfViewer", () => ({
  PdfViewer: ({ docId }: { docId: string }) => (
    <div data-testid="pdf-viewer" data-doc-id={docId} />
  ),
}));

vi.mock("./renderers/TextPreview", () => ({
  TextPreview: ({ docId }: { docId?: string }) => (
    <div data-testid="text-preview" data-doc-id={docId} />
  ),
}));

function makePreview(overrides: Partial<DocumentPreview> = {}): DocumentPreview {
  return {
    document_id: "doc-1",
    title: "Test",
    mime_type: "text/plain",
    translation_quality: null,
    translation_score: 0,
    metadata: {},
    snippet: "",
    view_count: 0,
    ...overrides,
  };
}

describe("PreviewPane dispatch", () => {
  it("dispatches application/pdf to PdfViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/pdf" })} />);
    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("PDF viewer receives the correct docId", () => {
    render(
      <PreviewPane preview={makePreview({ mime_type: "application/pdf", document_id: "abc-123" })} />
    );
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-doc-id", "abc-123");
  });

  it("does not dispatch application/pdf to TextPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/pdf" })} />);
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches text/plain to TextPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/plain" })} />);
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-viewer")).not.toBeInTheDocument();
  });

  it("dispatches text/markdown to TextPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/markdown" })} />);
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
  });
});
