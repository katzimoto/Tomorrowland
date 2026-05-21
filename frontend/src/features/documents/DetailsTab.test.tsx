import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DetailsTab } from "./DetailsTab";
import type { DocumentPreview } from "@/api/documents";

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
  it("renders the file name", () => {
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

  it("renders original language", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("fr")).toBeInTheDocument();
  });

  it("renders translation quality badge", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders processing status", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("Indexed")).toBeInTheDocument();
  });

  it("renders version number", () => {
    render(<DetailsTab preview={basePreview} />);
    const versionLabel = screen.getByText("Version");
    const row = versionLabel.closest("div");
    expect(row?.querySelector("dd")?.textContent).toContain("3");
    expect(screen.getByText(/latest/)).toBeInTheDocument();
  });

  it("renders created timestamp", () => {
    render(<DetailsTab preview={basePreview} />);
    // Just check the label is present; locale formatting varies
    expect(screen.getByText("Imported")).toBeInTheDocument();
  });

  it("renders updated timestamp when present", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(screen.getByText("Updated")).toBeInTheDocument();
  });

  it("renders truncated SHA-256 (first 12 chars + ellipsis)", () => {
    render(<DetailsTab preview={basePreview} />);
    const codes = document.querySelectorAll("code");
    const hashEl = Array.from(codes).find((c) => c.textContent?.includes("abcdef123456"));
    expect(hashEl).not.toBeUndefined();
    expect(hashEl?.textContent).toMatch(/abcdef123456…/);
  });

  it("copy button calls navigator.clipboard.writeText with full hash", () => {
    render(<DetailsTab preview={basePreview} />);
    const copyBtn = screen.getByRole("button", { name: /copy full sha-256/i });
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(basePreview.content_sha256);
  });

  it("omits source row when metadata has no source", () => {
    render(<DetailsTab preview={{ ...basePreview, metadata: {} }} />);
    expect(screen.queryByText("Source")).not.toBeInTheDocument();
  });

  it("shows source from metadata.connector_name", () => {
    render(
      <DetailsTab
        preview={{
          ...basePreview,
          metadata: { connector_name: "SharePoint" },
        }}
      />
    );
    expect(screen.getByText("SharePoint")).toBeInTheDocument();
  });

  it("shows source path from metadata.path", () => {
    render(
      <DetailsTab
        preview={{
          ...basePreview,
          metadata: { path: "/docs/reports/annual.pdf" },
        }}
      />
    );
    expect(screen.getByText("/docs/reports/annual.pdf")).toBeInTheDocument();
  });

  it("omits file size row when not in metadata", () => {
    render(<DetailsTab preview={{ ...basePreview, metadata: {} }} />);
    expect(screen.queryByText("File size")).not.toBeInTheDocument();
  });

  it("shows file size from metadata.file_size in KB", () => {
    render(
      <DetailsTab
        preview={{
          ...basePreview,
          metadata: { file_size: 51200 },
        }}
      />
    );
    expect(screen.getByText("50.0 KB")).toBeInTheDocument();
  });

  it("omits source_language row when null", () => {
    render(<DetailsTab preview={{ ...basePreview, source_language: null }} />);
    expect(screen.queryByText("Original language")).not.toBeInTheDocument();
  });

  it("omits SHA-256 row when content_sha256 is null", () => {
    render(<DetailsTab preview={{ ...basePreview, content_sha256: null }} />);
    expect(screen.queryByRole("button", { name: /copy full sha-256/i })).not.toBeInTheDocument();
  });

  it("renders using a definition list for keyboard navigation", () => {
    render(<DetailsTab preview={basePreview} />);
    expect(document.querySelector("dl")).toBeInTheDocument();
    expect(document.querySelectorAll("dt").length).toBeGreaterThan(0);
    expect(document.querySelectorAll("dd").length).toBeGreaterThan(0);
  });
});
