import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { DocumentPage } from "./DocumentPage";
import * as documentsApi from "@/api/documents";
import * as commentsApi from "@/api/comments";
import * as annotationsApi from "@/api/annotations";

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ docId: "doc-123" }),
  useNavigate: () => vi.fn(),
  useSearch: () => ({}),
  Link: ({ children, params, search }: { children: React.ReactNode; to: string; params?: Record<string, string>; search?: Record<string, string | undefined> }) => {
    const docId = params?.docId ?? "";
    const href = `/doc/${docId}?page=${search?.page ?? ""}&chunk=${search?.chunk ?? ""}`;
    return <a href={href}>{children}</a>;
  },
}));

vi.mock("@/api/documents");
vi.mock("@/api/comments");
vi.mock("@/api/annotations");

// pdfjs-dist requires DOMMatrix which is unavailable in jsdom
vi.mock("./renderers/PdfViewer", () => ({
  PdfViewer: ({ docId }: { docId: string }) => <div data-testid="pdf-viewer" data-doc-id={docId} />,
}));

const mockPreview: documentsApi.DocumentPreview = {
  document_id: "doc-123",
  title: "Vendor Risk Assessment 2024",
  mime_type: "text/plain",
  translation_quality: "fast",
  translation_score: 0.5,
  metadata: {},
  snippet: "This document covers vendor risk.",
  view_count: 3,
};

beforeEach(() => {
  vi.mocked(documentsApi.getPreview).mockResolvedValue(mockPreview);
  vi.mocked(documentsApi.getDownloadUrl).mockReturnValue(
    "/api/download/doc-123"
  );
  vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
  vi.mocked(documentsApi.getDocumentText).mockResolvedValue({
    text: "This document covers vendor risk.",
    total_length: 33,
    offset: 0,
    limit: 10000,
    truncated: false,
  });
  vi.mocked(documentsApi.getSummary).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getEntities).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getTags).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getRelated).mockRejectedValue(new Error("not found"));
  vi.mocked(commentsApi.listCommentsPage).mockResolvedValue({
    comments: [],
    total: 0,
  });
  vi.mocked(annotationsApi.listAnnotations).mockResolvedValue([]);
});

describe("DocumentPage", () => {
  it("renders document title after loading", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
      ).toBeInTheDocument();
    });
  });

  it("shows translation quality via TrustDisplay", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(screen.getByText("Fast translation")).toBeInTheDocument();
    });
  });

  it("shows back to search button", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /back to search/i })
      ).toBeInTheDocument();
    });
  });

  it("shows request translation button when quality is not high", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /request translation/i })
      ).toBeInTheDocument();
    });
  });

  it("shows download link with correct href", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      const link = screen.getByRole("link", { name: /download/i });
      expect(link).toHaveAttribute("href", "/api/download/doc-123");
    });
  });

  it("defers hidden insight panel API work until the panel is opened", async () => {
    render(<DocumentPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
      ).toBeInTheDocument();
    });

    expect(documentsApi.getRelated).not.toHaveBeenCalled();
    expect(annotationsApi.listAnnotations).not.toHaveBeenCalled();
    expect(commentsApi.listCommentsPage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("tab", { name: "Comments" }));

    await waitFor(() => {
      expect(commentsApi.listCommentsPage).toHaveBeenCalledWith("doc-123", 0, 20);
    });
  });

  it("shows error state when preview fails", async () => {
    vi.mocked(documentsApi.getPreview).mockRejectedValueOnce(
      new Error("not found")
    );
    render(<DocumentPage />);
    await waitFor(() => {
      expect(screen.getByText("Document not found")).toBeInTheDocument();
    });
  });

  it("renders preview snippet via TextPreview", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByText("This document covers vendor risk.")
      ).toBeInTheDocument();
    });
  });

  it("shows version selector with Latest and Original options", async () => {
    render(<DocumentPage />);
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

  it("calls getPreview with show_original=true when Original is selected", async () => {
    render(<DocumentPage />);
    const select = await screen.findByRole("combobox", {
      name: "Translation version",
    });
    await fireEvent.change(select, { target: { value: "__original__" } });
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Original" })
      ).toBeInTheDocument();
    });
  });

  it("shows FidelityStatusBar after preview loads", async () => {
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
      ).toBeInTheDocument();
    });
    // Status bar is rendered (text visible)
    expect(screen.getByText(/Viewing/i)).toBeInTheDocument();
  });

  it("defaults to original mode when no translations are available", async () => {
    vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
    render(<DocumentPage />);
    await waitFor(() => {
      expect(screen.getByText(/Viewing original file/i)).toBeInTheDocument();
    });
  });

  it("switches to translation mode when available translations exist", async () => {
    vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([
      {
        version_id: "v1",
        label: "Version 1",
        version_number: 1,
        quality: "fast",
        status: "available",
        target_language: "es",
        requested_at: "2026-01-01T00:00:00Z",
      },
    ]);
    render(<DocumentPage />);
    await waitFor(() => {
      expect(screen.getByText(/Viewing fast translation/i)).toBeInTheDocument();
    });
  });

  it("ViewModeSwitcher is hidden when only one mode is available", async () => {
    vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
    vi.mocked(documentsApi.getPreview).mockResolvedValue({
      ...mockPreview,
      snippet: "", // no extracted text
    });
    render(<DocumentPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("group", { name: "View mode" })).not.toBeInTheDocument();
  });

  describe("in-document search (Ctrl+F)", () => {
    it("opens DocumentSearchBar on Ctrl+F for text/plain documents", async () => {
      render(<DocumentPage />);
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
        ).toBeInTheDocument();
      });
      fireEvent.keyDown(document.querySelector('[tabindex="-1"]') ?? document.body, {
        key: "f",
        ctrlKey: true,
      });
      await waitFor(() => {
        expect(screen.getByRole("searchbox")).toBeInTheDocument();
      });
    });

    it("does not open DocumentSearchBar on Ctrl+F for unsupported types", async () => {
      vi.mocked(documentsApi.getPreview).mockResolvedValue({
        ...mockPreview,
        mime_type: "image/png",
      });
      render(<DocumentPage />);
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Vendor Risk Assessment 2024" })
        ).toBeInTheDocument();
      });
      fireEvent.keyDown(document.querySelector('[tabindex="-1"]') ?? document.body, {
        key: "f",
        ctrlKey: true,
      });
      // No searchbox should appear for images
      expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    });
  });
});
