import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DetailsTab } from "./DetailsTab";
import type { DocumentPreview } from "@/api/documents";

vi.mock("@/api/documents", () => ({
  listUserTags: vi.fn().mockResolvedValue({ document_id: "", tags: [] }),
  addUserTag: vi.fn(),
  deleteUserTag: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...props }: Record<string, unknown>) => (
    <a href={(props.to as string) ?? ""} {...props} aria-label="mock link">{children as React.ReactNode}</a>
  ),
  useSearch: () => ({}),
}));

const basePreview: DocumentPreview = {
  document_id: "doc-1",
  title: "Annual Report 2024.pdf",
  mime_type: "application/pdf",
  translation_quality: "high",
  translation_score: 0.9,
  metadata: {},
  snippet: "Some text",
  view_count: 5,
  version_number: 3,
  is_latest: true,
  source_language: "fr",
  target_language: "en",
  status: "indexed",
  content_sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  created_at: "2024-01-15T10:30:00.000Z",
  updated_at: "2024-06-01T08:00:00.000Z",
};

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("DetailsTab", () => {
  it("renders the file name in the open File section", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("Annual Report 2024.pdf")).toBeInTheDocument();
  });

  it("renders human-readable file type", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("PDF Document")).toBeInTheDocument();
  });

  it("renders MIME type in a code element", () => {
    render(<DetailsTab preview={basePreview} />);
    const code = document.querySelector("code");
    expect(code?.textContent).toContain("application/pdf");
  });

  it("shows collapsed section headers for Source and Processing", () => {
    render(<DetailsTab preview={basePreview} />);
    // File section is open; Processing header is visible
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("renders source when metadata has connector_name", () => {
    render(
      <DetailsTab
        preview={{ ...basePreview, metadata: { connector_name: "SharePoint", path: "/a/b" } }}
      />
    );
    // Source section starts collapsed; click to open
    fireEvent.click(screen.getByText("Source"));
    expect(screen.getByText("SharePoint")).toBeInTheDocument();
  });

  it("renders source path from metadata.path", () => {
    render(
      <DetailsTab
        preview={{ ...basePreview, metadata: { source: "Local", path: "/docs/reports/a.pdf" } }}
      />
    );
    fireEvent.click(screen.getByText("Source"));
    expect(screen.getByText(/docs\/reports\/a.pdf/)).toBeInTheDocument();
  });

  it("renders processing details when Processing section is opened", () => {
    render(<DetailsTab preview={basePreview} />);
    fireEvent.click(screen.getByText("Processing"));
    expect(screen.getByText("Indexed")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Imported")).toBeInTheDocument();
    expect(screen.getByText("Updated")).toBeInTheDocument();
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText(/latest/)).toBeInTheDocument();
  });

  it("renders truncated SHA-256", () => {
    render(<DetailsTab preview={basePreview} />);
    fireEvent.click(screen.getByText("Processing"));
    const codes = document.querySelectorAll("code");
    const hashEl = Array.from(codes).find((c) => c.textContent?.includes("abcdef123456"));
    expect(hashEl).not.toBeUndefined();
    expect(hashEl?.textContent).toMatch(/abcdef123456…/);
  });

  it("copy button calls clipboard with full hash", () => {
    render(<DetailsTab preview={basePreview} />);
    fireEvent.click(screen.getByText("Processing"));
    const copyBtn = screen.getByRole("button", { name: /copy full sha-256/i });
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(basePreview.content_sha256);
  });

  it("omits file size row when not in metadata", () => {
    render(<DetailsTab preview={{ ...basePreview, metadata: {} }} />);
    expect(screen.queryByText("File size")).not.toBeInTheDocument();
  });

  it("shows file size from metadata.file_size", () => {
    render(
      <DetailsTab
        preview={{ ...basePreview, metadata: { file_size: 51200 } }}
      />
    );
    expect(screen.getByText("50.0 KB")).toBeInTheDocument();
  });

  it("omits source section when metadata has no source", () => {
    render(<DetailsTab preview={{ ...basePreview, metadata: {} }} />);
    expect(screen.queryByText("Source")).not.toBeInTheDocument();
  });

  it("omits source_language row when null", () => {
    render(<DetailsTab preview={{ ...basePreview, source_language: null }} />);
    expect(screen.queryByText("Original language")).not.toBeInTheDocument();
  });

  it("omits SHA-256 when content_sha256 is null", () => {
    render(<DetailsTab preview={{ ...basePreview, content_sha256: null, metadata: { source: "x", path: "/y" } }} />);
    fireEvent.click(screen.getByText("Processing"));
    expect(screen.queryByRole("button", { name: /copy full sha-256/i })).not.toBeInTheDocument();
  });

  it("renders My Tags section when docId is provided", () => {
    render(<DetailsTab preview={basePreview} docId="doc-1" />);
    expect(screen.getByText("My Tags")).toBeInTheDocument();
  });

  it("renders Metadata section with Fields/Raw JSON toggle", () => {
    render(
      <DetailsTab
        preview={{ ...basePreview, metadata: { key1: "val1", key2: 42 } }}
      />
    );
    expect(screen.getByText("Metadata")).toBeInTheDocument();
    expect(screen.getByText("Fields")).toBeInTheDocument();
    expect(screen.getByText("Raw JSON")).toBeInTheDocument();
  });
});
