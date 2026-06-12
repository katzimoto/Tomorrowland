import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminSourceHealthPage } from "./AdminSourceHealthPage";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    listSources: vi.fn(),
    getSourceHealth: vi.fn(),
  },
}));

const sourceDefaults = {
  path: null,
  source_language: "en",
  enabled: true,
  created_at: "2025-01-01",
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
} as const;

function makeQa(overrides: Partial<adminApi.SourceHealthResponse> = {}): adminApi.SourceHealthResponse {
  return {
    source_id: "src-1",
    checked_at: "2026-01-01T12:00:00Z",
    total_documents: 10,
    indexed_documents: 8,
    pending_documents: 1,
    failed_documents: 1,
    empty_chunks: 0,
    missing_content: 0,
    missing_metadata: 0,
    missing_title: 0,
    ocr_eligible: 1,
    ocr_maybe_needed: 1,
    index_lag_count: 0,
    issues: ["1 PDF(s) with empty text may need OCR"],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
    { ...sourceDefaults, id: "src-1", name: "Source One", type: "folder" },
  ]);
  vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(makeQa());
});

describe("AdminSourceHealthPage", () => {
  it("renders the Source Health heading", async () => {
    render(<AdminSourceHealthPage />);
    expect(await screen.findByRole("heading", { name: /source health/i })).toBeInTheDocument();
  });

  it("shows summary cards with aggregated document counts", async () => {
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("10")).toBeInTheDocument(); // total
    expect(screen.getByText("8")).toBeInTheDocument(); // indexed
    // "1" appears as both pending count and failed count
    const ones = screen.getAllByText("1");
    expect(ones.length).toBeGreaterThanOrEqual(2);
  });

  it("shows empty state when there are no sources", async () => {
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([]);
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText(/no sources configured/i)).toBeInTheDocument();
  });

  it("renders source name as a link in the table", async () => {
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("Source One")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /source one/i });
    expect(link).toHaveAttribute("href", "/admin/sources/src-1");
  });

  it("shows healthy badge (green) when no issues and no failures", async () => {
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({ failed_documents: 0, issues: [] }),
    );
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    const badge = screen.getByText("Healthy");
    expect(badge.closest("[class*=\"success\"]") || badge.closest("[data-variant=\"success\"]")).toBeTruthy();
  });

  it("shows degraded badge (yellow) when issues exist but no failures", async () => {
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({ failed_documents: 0, issues: ["Some minor issues"] }),
    );
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("Degraded")).toBeInTheDocument();
  });

  it("shows failed badge (red) when failed_documents > 0", async () => {
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({ failed_documents: 3, issues: ["Something went wrong"] }),
    );
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("Failed")).toBeInTheDocument();
  });

  it("shows 'No checks run' when QA has not been run", async () => {
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({ checked_at: null as unknown as string, failed_documents: 0, issues: [] }),
    );
    render(<AdminSourceHealthPage />);
    expect(await screen.findByText("No checks run")).toBeInTheDocument();
  });

  it("expands a row to show issue details and recommended actions", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({
        issues: [
          "2 indexed document(s) have empty or missing content text",
          "1 PDF(s) with empty text may need OCR",
        ],
      }),
    );
    render(<AdminSourceHealthPage />);

    await screen.findByText("Source One");

    const expandBtn = screen.getByRole("button", { name: /expand details/i });
    await user.click(expandBtn);

    expect(await screen.findByText(/empty or missing content/i)).toBeInTheDocument();
    expect(screen.getByText(/may need ocr/i)).toBeInTheDocument();
    expect(screen.getByText(/check document payloads/i)).toBeInTheDocument();
    expect(screen.getByText(/enable ocr/i)).toBeInTheDocument();
  });

  it("shows the no-QA message when expanding a source with no check data", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValue(
      makeQa({ checked_at: null as unknown as string, failed_documents: 0, issues: [] }),
    );
    render(<AdminSourceHealthPage />);

    await screen.findByText("Source One");

    const expandBtn = screen.getByRole("button", { name: /expand details/i });
    await user.click(expandBtn);

    expect(await screen.findByText(/click a source/i)).toBeInTheDocument();
  });

  it("triggers a QA check when Run QA button is clicked", async () => {
    const user = userEvent.setup();

    render(<AdminSourceHealthPage />);

    await screen.findByText("Source One");

    // Reset call count after initial load
    vi.mocked(adminApi.adminApi.getSourceHealth).mockClear();
    vi.mocked(adminApi.adminApi.getSourceHealth).mockResolvedValueOnce(
      makeQa({ checked_at: "2026-06-01T00:00:00Z" }),
    );

    const runBtn = screen.getByRole("button", { name: /run qa check/i });
    await user.click(runBtn);

    expect(adminApi.adminApi.getSourceHealth).toHaveBeenCalledWith("src-1");
  });
});
