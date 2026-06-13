import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { PreviewPane } from "./PreviewPane";
import type { DocumentPreview } from "@/api/documents";

// Stub heavy renderers to keep PreviewPane dispatch tests fast
vi.mock("./renderers/PdfViewer", () => ({
  PdfViewer: ({ docId, searchQuery }: { docId: string; searchQuery?: string }) => (
    <div data-testid="pdf-viewer" data-doc-id={docId} data-search-query={searchQuery} />
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
  CodeViewer: ({ docId, mimeType, searchQuery }: { docId: string; mimeType: string; searchQuery?: string }) => (
    <div data-testid="code-viewer" data-doc-id={docId} data-mime={mimeType} data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/TablePreview", () => ({
  TablePreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="table-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/ArchivePreview", () => ({
  ArchivePreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="archive-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/EmailManifestPreview", () => ({
  EmailManifestPreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="email-manifest-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/OfficeManifestPreview", () => ({
  OfficeManifestPreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="office-manifest-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/SheetManifestPreview", () => ({
  SheetManifestPreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="sheet-manifest-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/SlidesPreview", () => ({
  SlidesPreview: ({ searchQuery }: { searchQuery?: string }) => (
    <div data-testid="slides-preview" data-search-query={searchQuery} />
  ),
}));

vi.mock("./renderers/MarkdownPreview", () => ({
  MarkdownPreview: ({ docId, fallbackText }: { docId: string; fallbackText?: string }) => (
    <div
      data-testid="markdown-preview"
      data-doc-id={docId}
      data-fallback={fallbackText}
    />
  ),
}));

vi.mock("./renderers/TextPreview", () => ({
  TextPreview: ({
    docId,
    showOriginal,
    translationVersionId,
    searchQuery,
    activeSearchIndex,
  }: {
    docId?: string;
    showOriginal?: boolean;
    translationVersionId?: string;
    searchQuery?: string;
    activeSearchIndex?: number;
  }) => (
    <div
      data-testid="text-preview"
      data-doc-id={docId}
      data-show-original={showOriginal ? "true" : undefined}
      data-version-id={translationVersionId}
      data-search-query={searchQuery}
      data-active-index={activeSearchIndex}
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

  it("dispatches text/markdown to MarkdownPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/markdown" })} />);
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("text-preview")).not.toBeInTheDocument();
  });

  it("dispatches text/x-markdown to MarkdownPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "text/x-markdown" })} />);
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });

  it("dispatches application/markdown to MarkdownPreview", () => {
    render(<PreviewPane preview={makePreview({ mime_type: "application/markdown" })} />);
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });

  it("dispatches text/plain with .md title to MarkdownPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type: "text/plain",
          title: "README.md",
        })}
      />
    );
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });

  it("dispatches text/plain with .markdown title to MarkdownPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type: "text/plain",
          title: "doc.markdown",
        })}
      />
    );
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });

  it("dispatches text/plain without .md title to TextPreview", () => {
    render(
      <PreviewPane
        preview={makePreview({
          mime_type: "text/plain",
          title: "readme.txt",
        })}
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
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

  it("extracted mode overrides HTML to TextPreview with showOriginal", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "text/html" })}
        activeMode="extracted"
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.getByTestId("text-preview")).toHaveAttribute("data-show-original", "true");
  });

  it("translation mode overrides HTML to TextPreview with translationVersionId", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "text/html" })}
        activeMode="translation"
        selectedVersionId="v-html-1"
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.getByTestId("text-preview")).toHaveAttribute("data-version-id", "v-html-1");
    expect(screen.getByTestId("text-preview")).not.toHaveAttribute("data-show-original", "true");
  });

  it("original mode overrides HTML to TextPreview with showOriginal", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "text/html" })}
        activeMode="original"
      />
    );
    expect(screen.getByTestId("text-preview")).toBeInTheDocument();
    expect(screen.getByTestId("text-preview")).toHaveAttribute("data-show-original", "true");
  });

  it("image/png in original mode is not affected by the HTML text override", () => {
    render(
      <PreviewPane
        preview={makePreview({ mime_type: "image/png" })}
        activeMode="original"
      />
    );
    expect(screen.getByTestId("image-viewer")).toBeInTheDocument();
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

  describe("search prop passing", () => {
    it("passes docId to MarkdownPreview for text/markdown", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "text/markdown", document_id: "md-doc-1" })}
          searchQuery="md"
          activeSearchIndex={1}
        />
      );
      expect(screen.getByTestId("markdown-preview")).toHaveAttribute("data-doc-id", "md-doc-1");
    });
    it("passes searchQuery to TextPreview for text/plain", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "text/plain" })}
          searchQuery="test"
          activeSearchIndex={2}
        />
      );
      const tp = screen.getByTestId("text-preview");
      expect(tp).toHaveAttribute("data-search-query", "test");
      expect(tp).toHaveAttribute("data-active-index", "2");
    });

    it("routes DOCX to the office manifest viewer in default mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" })}
          searchQuery="word"
          activeSearchIndex={1}
        />
      );
      expect(screen.getByTestId("office-manifest-preview")).toHaveAttribute(
        "data-search-query",
        "word",
      );
    });

    it("routes DOCX to extracted text in extracted mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" })}
          searchQuery="word"
          activeMode="extracted"
        />
      );
      expect(screen.getByTestId("text-preview")).toHaveAttribute("data-search-query", "word");
    });

    it("passes searchQuery to TextPreview for extracted mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/pdf" })}
          activeMode="extracted"
          searchQuery="extracted"
          activeSearchIndex={0}
        />
      );
      const tp = screen.getByTestId("text-preview");
      expect(tp).toHaveAttribute("data-search-query", "extracted");
    });

    it("passes searchQuery to PdfViewer for application/pdf", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/pdf" })}
          searchQuery="pdfterm"
        />
      );
      const pv = screen.getByTestId("pdf-viewer");
      expect(pv).toHaveAttribute("data-search-query", "pdfterm");
    });

    it("routes XLSX to the sheet manifest viewer in default mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })}
          searchQuery="cellval"
        />
      );
      expect(screen.getByTestId("sheet-manifest-preview")).toHaveAttribute(
        "data-search-query",
        "cellval",
      );
    });

    it("keeps legacy XLS on the extracted-text table preview", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/vnd.ms-excel" })}
          searchQuery="cellval"
        />
      );
      expect(screen.getByTestId("table-preview")).toHaveAttribute("data-search-query", "cellval");
    });

    it("passes searchQuery to archive preview for zip MIME", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/zip" })}
          searchQuery="archive"
        />
      );
      expect(screen.getByTestId("archive-preview")).toHaveAttribute("data-search-query", "archive");
    });

    it("routes rfc822 to the manifest viewer in default mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "message/rfc822" })}
          searchQuery="email"
        />
      );
      expect(screen.getByTestId("email-manifest-preview")).toHaveAttribute(
        "data-search-query",
        "email",
      );
    });

    it("routes rfc822 to the extracted-text preview in extracted mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "message/rfc822" })}
          searchQuery="email"
          activeMode="extracted"
        />
      );
      expect(screen.getByTestId("text-preview")).toHaveAttribute("data-search-query", "email");
    });

    it("routes PPTX to the office manifest viewer in default mode", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" })}
          searchQuery="slide"
        />
      );
      expect(screen.getByTestId("office-manifest-preview")).toHaveAttribute(
        "data-search-query",
        "slide",
      );
    });

    it("passes searchQuery to CodeViewer for application/json", () => {
      render(
        <PreviewPane
          preview={makePreview({ mime_type: "application/json" })}
          searchQuery="code"
        />
      );
      expect(screen.getByTestId("code-viewer")).toHaveAttribute("data-search-query", "code");
    });
  });
});
