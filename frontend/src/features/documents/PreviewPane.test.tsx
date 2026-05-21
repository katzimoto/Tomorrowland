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

vi.mock("./renderers/ImageViewer", () => ({
  ImageViewer: ({ docId, mimeType }: { docId: string; mimeType: string }) => (
    <div data-testid="image-viewer" data-doc-id={docId} data-mime={mimeType} />
  ),
}));

vi.mock("./renderers/MediaPreview", () => ({
  MediaPreview: ({ docId, mimeType }: { docId: string; mimeType: string }) => (
    <div data-testid="media-preview" data-doc-id={docId} data-mime={mimeType} />
  ),
}));

vi.mock("./renderers/CodeViewer", () => ({
  CodeViewer: ({ docId, mimeType }: { docId: string; mimeType: string }) => (
    <div data-testid="code-viewer" data-doc-id={docId} data-mime={mimeType} />
  ),
}));

vi.mock("./renderers/TextPreview", () => ({
  TextPreview: ({
    docId,
    showOriginal,
    translationVersionId,
  }: {
    docId?: string;
    showOriginal?: boolean;
    translationVersionId?: string;
  }) => (
    <div
      data-testid="text-preview"
      data-doc-id={docId}
      data-show-original={showOriginal ? "true" : undefined}
      data-version-id={translationVersionId}
    />
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

  it("extracted mode overrides PDF to TextPreview with showOriginal", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "application/pdf" })}
        activeMode="extracted"
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-viewer")).not.toBeInTheDocument();
    expect(screen.getByTestId("text-preview")).toHaveAttribute("data-show-original", "true");
  });

  it("translation mode overrides PDF to TextPreview with translationVersionId", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "application/pdf" })}
        activeMode="translation"
        selectedVersionId="v-abc"
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-viewer")).not.toBeInTheDocument();
    expect(screen.getByTestId("text-preview")).toHaveAttribute("data-version-id", "v-abc");
  });

  it("original mode still dispatches PDF to PdfViewer", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "application/pdf" })}
        activeMode="original"
      />
    );
    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("extracted mode does not override HTML to TextPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "text/html" })}
        activeMode="extracted"
      />
    );
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches image/png to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/png" })} />);
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
  });

  it("dispatches image/jpeg to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/jpeg" })} />);
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
  });

  it("dispatches image/webp to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/webp" })} />);
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
  });

  it("dispatches image/gif to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/gif" })} />);
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
  });

  it("dispatches image/svg+xml to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/svg+xml" })} />);
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
  });

  it("passes mimeType to ImageViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "image/png", document_id: "img-1" })} />);
    const viewer = screen.getByTestId("image-viewer");
    expect(viewer).toHaveAttribute("data-mime", "image/png");
    expect(viewer).toHaveAttribute("data-doc-id", "img-1");
  });

  it("dispatches application/json to CodeViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/json" })} />);
    expect(screen.getByTestId("code-viewer")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches text/xml to CodeViewer", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/xml" })} />);
    expect(screen.getByTestId("code-viewer")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches text/plain to TextPreview (not CodeViewer)", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/plain" })} />);
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("code-viewer")).not.toBeInTheDocument();
  });

  it("dispatches audio/mpeg to MediaPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "audio/mpeg" })} />);
    expect(screen.getByTestId("media-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches video/mp4 to MediaPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "video/mp4" })} />);
    expect(screen.getByTestId("media-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });
});
