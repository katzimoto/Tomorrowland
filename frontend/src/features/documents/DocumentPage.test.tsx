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
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("@/api/documents");
vi.mock("@/api/comments");
vi.mock("@/api/annotations");

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
});
