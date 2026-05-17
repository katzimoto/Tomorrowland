import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { DocumentToolbar } from "./DocumentToolbar";
import type { DocumentPreview } from "@/api/documents";
import * as documentsApi from "@/api/documents";

vi.mock("@/api/documents");
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const mockPreview: DocumentPreview = {
  document_id: "doc-1",
  title: "Vendor Risk Assessment",
  mime_type: "text/plain",
  translation_quality: "fast",
  metadata: {},
  snippet: "",
  view_count: 2,
};

beforeEach(() => {
  vi.mocked(documentsApi.getDownloadUrl).mockReturnValue("/api/download/doc-1");
  vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
});

describe("DocumentToolbar", () => {
  it("renders document title", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("heading", { name: "Vendor Risk Assessment" })
    ).toBeInTheDocument();
  });

  it("shows back to search button", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("button", { name: /back to search/i })
    ).toBeInTheDocument();
  });

  it("shows download link", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/api/download/doc-1"
    );
  });

  it("shows request translation button when quality is not high", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("button", { name: /request translation/i })
    ).toBeInTheDocument();
  });

  it("hides request translation when quality is already high", () => {
    render(
      <DocumentToolbar
        preview={{ ...mockPreview, translation_quality: "high" }}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(
      screen.queryByRole("button", { name: /request translation/i })
    ).not.toBeInTheDocument();
  });

  it("shows trust display", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
      />
    );
    expect(screen.getByText("Fast translation")).toBeInTheDocument();
  });
});
