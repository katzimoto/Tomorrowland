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

vi.mock("./renderers/HtmlPreview", () => ({
  HtmlPreview: ({ html }: { html: string }) => (
    <div data-testid="html-preview" data-html={html} />
  ),
}));

vi.mock("./renderers/ArchivePreview", () => ({
  ArchivePreview: ({ text }: { text: string }) => (
    <div data-testid="archive-preview" data-text={text} />
  ),
}));

vi.mock("./renderers/EmailPreview", () => ({
  EmailPreview: () => <div data-testid="email-preview" />,
}));

vi.mock("./renderers/SlidesPreview", () => ({
  SlidesPreview: () => <div data-testid="slides-preview" />,
}));

vi.mock("./renderers/UnsupportedPreview", () => ({
  UnsupportedPreview: ({ mimeType }: { mimeType: string }) => (
    <div data-testid="unsupported-preview" data-mime={mimeType} />
  ),
}));

vi.mock("./renderers/TablePreview", () => ({
  TablePreview: () => <div data-testid="table-preview" />,
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

  it("dispatches audio/ogg to MediaPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "audio/ogg" })} />);
    expect(screen.getByTestId("media-preview")).toBeInTheDocument();
  });

  it("dispatches video/webm to MediaPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "video/webm" })} />);
    expect(screen.getByTestId("media-preview")).toBeInTheDocument();
  });

  it("dispatches text/html to HtmlPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/html" })} />);
    expect(screen.getByTestId("html-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches text/csv to TextPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/csv" })} />);
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
  });

  it("dispatches application/zip to ArchivePreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/zip" })} />);
    expect(screen.getByTestId("archive-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches application/x-tar to ArchivePreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/x-tar" })} />);
    expect(screen.getByTestId("archive-preview")).toBeInTheDocument();
  });

  it("dispatches message/rfc822 to EmailPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "message/rfc822" })} />);
    expect(screen.getByTestId("email-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches application/vnd.ms-outlook to EmailPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/vnd.ms-outlook" })} />);
    expect(screen.getByTestId("email-preview")).toBeInTheDocument();
  });

  it("dispatches DOCX to TextPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        })}
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
  });

  it("dispatches application/rtf to TextPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/rtf" })} />);
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
  });

  it("dispatches XLSX to TablePreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type:
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })}
      />
    );
    expect(screen.getByTestId("table-preview")).toBeInTheDocument();
  });

  it("dispatches PPTX to SlidesPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type:
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        })}
      />
    );
    expect(screen.getByTestId("slides-preview")).toBeInTheDocument();
  });

  it("dispatches unknown MIME to UnsupportedPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "application/octet-stream" })}
      />
    );
    expect(screen.getByTestId("unsupported-preview")).toBeInTheDocument();
    expect(screen.getByTestId("unsupported-preview")).toHaveAttribute(
      "data-mime",
      "application/octet-stream"
    );
  });
});
