import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { render } from "@/test/render";
import { AdminSourceDetailPage } from "./AdminSourceDetailPage";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    getSource: vi.fn(),
    getSourceDocuments: vi.fn(),
    listGroups: vi.fn(),
    grantPermission: vi.fn(),
    revokePermission: vi.fn(),
    updateSource: vi.fn(),
    deleteSource: vi.fn(),
    requeueDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
}));

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual("@tanstack/react-router");
  return {
    ...(actual as object),
    useParams: () => ({ sourceId: "src-1" }),
    useNavigate: () => vi.fn(),
  };
});

function makeDoc(overrides: Partial<adminApi.SourceDocument> = {}): adminApi.SourceDocument {
  return {
    id: "doc-1",
    title: "Test Document",
    external_id: "ext-1",
    status: "indexed",
    mime_type: "application/pdf",
    source_language: "en",
    translation_quality: "fast",
    created_at: "2026-01-01T00:00:00Z",
    total_jobs: 4,
    succeeded_jobs: 3,
    pending_jobs: 0,
    failed_jobs: 1,
    jobs: [],
    parser_name: "PdfExtractor",
    fallback_chain: ["PdfExtractor"],
    extraction_status: "extracted",
    extraction_confidence: 0.95,
    extraction_duration_ms: 1200,
    char_count: 5000,
    chunk_count: 3,
    ocr_needed: false,
    ocr_performed: false,
    translation_status: "fast",
    layout_blocks_available: true,
    table_block_count: 2,
    figure_block_count: 1,
    last_error: null,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<adminApi.ParserSummary> = {}): adminApi.ParserSummary {
  return {
    documents_by_parser: { PdfExtractor: 3, PlainExtractor: 1 },
    total_extracted: 4,
    total_ocr_needed: 0,
    total_failed: 0,
    total_documents: 4,
    avg_char_count: 5000,
    ...overrides,
  };
}

const mockSource = {
  id: "src-1",
  name: "Test Source",
  type: "folder",
  path: "/data",
  source_language: "en",
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
  last_sync_status: null,
  last_sync_indexed: null,
  last_sync_skipped: null,
  last_sync_failed: null,
  last_sync_error: null,
  last_sync_at: null,
  last_validation_status: null,
  last_validation_error: null,
  last_validated_at: null,
  schedule: null,
  config: {},
  groups: [],
};

beforeEach(() => {
  vi.mocked(adminApi.adminApi.getSource).mockResolvedValue(mockSource);
  vi.mocked(adminApi.adminApi.listGroups).mockResolvedValue([]);
  vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
    documents: [],
    total: 0,
    parser_summary: makeSummary({ total_documents: 0, total_extracted: 0 }),
  });
});

describe("AdminParserStrategy", () => {
  it("shows the Parser Strategy heading", async () => {
    render(<AdminSourceDetailPage />);
    expect(await screen.findByText("Parser Strategy")).toBeInTheDocument();
  });

  it("shows no parser data when parser_summary is missing", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [],
      total: 0,
    });
    render(<AdminSourceDetailPage />);
    expect(
      await screen.findByText("No parser data available yet."),
    ).toBeInTheDocument();
  });

  it("renders parser summary stats for extracted documents", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc(),
        makeDoc({ id: "doc-2", parser_name: "PlainExtractor", extraction_status: "extracted" }),
      ],
      total: 2,
      parser_summary: makeSummary({
        total_documents: 2,
        total_extracted: 2,
        documents_by_parser: { PdfExtractor: 1, PlainExtractor: 1 },
      }),
    });
    render(<AdminSourceDetailPage />);
    // Wait for both sections to finish loading
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      expect(screen.getByText("2 / 2")).toBeInTheDocument();
    });
    await waitFor(() => {
      const headings = screen.getAllByText("PdfExtractor");
      expect(headings.length).toBeGreaterThanOrEqual(1);
    });
    await waitFor(() => {
      const headings = screen.getAllByText("PlainExtractor");
      expect(headings.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders layout-aware document metadata", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({ layout_blocks_available: true, table_block_count: 3, figure_block_count: 2 }),
      ],
      total: 1,
      parser_summary: makeSummary({ total_documents: 1 }),
    });
    render(<AdminSourceDetailPage />);
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      const yesElements = screen.getAllByText("Yes");
      expect(yesElements.length).toBeGreaterThanOrEqual(1);
    });
    await waitFor(() => {
      expect(screen.getByText(/3 Tables/)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(/2 Figures/)).toBeInTheDocument();
    });
  });

  it("shows extraction status badge for pending documents", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({
          extraction_status: "pending",
          parser_name: null,
          char_count: 0,
          chunk_count: 0,
        }),
      ],
      total: 1,
      parser_summary: makeSummary({ total_documents: 1, total_extracted: 0 }),
    });
    render(<AdminSourceDetailPage />);
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      const badges = screen.getAllByText("pending");
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
    await waitFor(() => {
      expect(screen.getByText("Unknown")).toBeInTheDocument();
    });
  });

  it("shows failed extraction badge with error message", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({
          id: "failed-doc",
          extraction_status: "pending",
          parser_name: null,
          last_error: "PDF parsing failed: corrupted file",
        }),
      ],
      total: 1,
      parser_summary: makeSummary({
        total_documents: 1,
        total_extracted: 0,
        total_failed: 1,
      }),
    });
    render(<AdminSourceDetailPage />);
    await waitFor(() => {
      expect(
        screen.getByText("PDF parsing failed: corrupted file"),
      ).toBeInTheDocument();
    });
  });

  it("shows OCR needed badge for image documents", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({
          mime_type: "image/png",
          ocr_needed: true,
          ocr_performed: false,
          parser_name: "OcrExtractor",
        }),
      ],
      total: 1,
      parser_summary: makeSummary({ total_documents: 1, total_ocr_needed: 1 }),
    });
    render(<AdminSourceDetailPage />);
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      // Table header also says "OCR needed" so there will be multiple
      const ocrElements = screen.getAllByText("OCR needed");
      expect(ocrElements.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows OCR done badge when OCR was performed", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({
          mime_type: "image/png",
          ocr_needed: true,
          ocr_performed: true,
          parser_name: "OcrExtractor",
        }),
      ],
      total: 1,
      parser_summary: makeSummary({ total_documents: 1 }),
    });
    render(<AdminSourceDetailPage />);
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      expect(screen.getByText("OCR done")).toBeInTheDocument();
    });
  });

  it("shows Unknown for missing parser metadata", async () => {
    vi.mocked(adminApi.adminApi.getSourceDocuments).mockResolvedValue({
      documents: [
        makeDoc({
          parser_name: null,
          extraction_status: "pending",
          char_count: null,
          chunk_count: null,
        }),
      ],
      total: 1,
      parser_summary: makeSummary({ total_documents: 1, total_extracted: 0 }),
    });
    render(<AdminSourceDetailPage />);
    await screen.findByText("Parser Strategy");
    await waitFor(() => {
      const unknowns = screen.getAllByText("Unknown");
      expect(unknowns.length).toBeGreaterThanOrEqual(1);
    });
  });
});
