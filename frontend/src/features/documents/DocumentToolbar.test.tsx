import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
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
  translation_score: 0.5,
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
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("heading", { name: "Vendor Risk Assessment" })
    ).toBeInTheDocument();
  });

  it("shows download button", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("button", { name: /download text/i })
    ).toBeInTheDocument();
  });

  it("shows back to search button", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("button", { name: /back to search/i })
    ).toBeInTheDocument();
  });

  it("shows download button with correct label", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("button", { name: /download text/i })
    ).toBeInTheDocument();
  });

  it("shows request translation button when quality is not high", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
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
        availableModes={["original", "translation"]}
        activeMode="translation"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
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
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByText("Fast translation")).toBeInTheDocument();
  });

  it("shows image zoom controls when showImageControls is true", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        showImageControls={true}
        imageZoom={null}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        onImageZoomChange={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset zoom" })).toBeInTheDocument();
  });

  it("hides image zoom controls when showImageControls is false", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        showImageControls={false}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: "Zoom in" })).not.toBeInTheDocument();
  });

  it("shows Fit label when imageZoom is null", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        showImageControls={true}
        imageZoom={null}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        onImageZoomChange={vi.fn()}
      />
    );
    expect(screen.getByText("Fit")).toBeInTheDocument();
  });

  it("shows zoom percentage label when imageZoom is set", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        showImageControls={true}
        imageZoom={150}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        onImageZoomChange={vi.fn()}
      />
    );
    expect(screen.getByText("150%")).toBeInTheDocument();
  });

  it("zoom in button calls onImageZoomChange", () => {
    const onImageZoomChange = vi.fn();
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        showImageControls={true}
        imageZoom={100}
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        onImageZoomChange={onImageZoomChange}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(onImageZoomChange).toHaveBeenCalledWith(125);
  });

  it("shows search button when searchable is true", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        searchable={true}
        searchOpen={false}
        onSearchToggle={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Search within document" })).toBeInTheDocument();
  });

  it("hides search button when searchable is false", () => {
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        searchable={false}
      />
    );
    expect(screen.queryByRole("button", { name: "Search within document" })).not.toBeInTheDocument();
  });

  it("search button toggles aria-pressed state", () => {
    const onSearchToggle = vi.fn();
    render(
      <DocumentToolbar
        preview={mockPreview}
        selectedVersionId={undefined}
        showOriginal={false}
        availableModes={["original"]}
        activeMode="original"
        onVersionChange={vi.fn()}
        onShowOriginalChange={vi.fn()}
        onModeChange={vi.fn()}
        searchable={true}
        searchOpen={true}
        onSearchToggle={onSearchToggle}
      />
    );
    const btn = screen.getByRole("button", { name: "Search within document" });
    expect(btn).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(btn);
    expect(onSearchToggle).toHaveBeenCalled();
  });
});
