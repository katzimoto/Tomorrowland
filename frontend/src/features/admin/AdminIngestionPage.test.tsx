import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminIngestionPage } from "./AdminIngestionPage";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    getIngestionStatus: vi.fn(),
    getDocumentTimeline: vi.fn(),
    retryDocument: vi.fn(),
    reprocessDocument: vi.fn(),
    reocrDocument: vi.fn(),
    retranslateDocument: vi.fn(),
    reembedDocument: vi.fn(),
  },
}));

const mockJob = {
  id: "job-1",
  document_id: "doc-1",
  source_id: "src-1",
  document_title: "Test Document",
  source_name: "Test Source",
  job_type: "parse",
  status: "completed",
  stage: "extract",
  attempts: 1,
  max_attempts: 5,
  last_error: null,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:05:00Z",
};

const mockFailedJob = {
  ...mockJob,
  id: "job-2",
  document_id: "doc-2",
  document_title: "Failed Doc",
  job_type: "vectorize",
  status: "failed",
  attempts: 3,
  last_error: "Connection timeout after 30s: Qdrant unavailable",
  updated_at: "2026-01-15T10:10:00Z",
};

const mockEmptyResponse = {
  jobs: [],
  total: 0,
  summary: {},
};

const mockPopulatedResponse = {
  jobs: [mockJob, mockFailedJob],
  total: 2,
  summary: { pending: 0, running: 0, completed: 1, failed: 1 },
};

const mockTimelineResponse = {
  document_id: "doc-1",
  document_title: "Test Document",
  source_name: "Test Source",
  stages: [
    {
      stage: "parsed",
      status: "completed" as const,
      at: "2026-01-15T10:05:00Z",
      duration_ms: 30000,
      error: null,
    },
    {
      stage: "embedded",
      status: "failed" as const,
      at: "2026-01-15T10:10:00Z",
      duration_ms: null,
      error: "UnexpectedResponse:process",
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue(mockPopulatedResponse);
  vi.mocked(adminApi.adminApi.getDocumentTimeline).mockResolvedValue(mockTimelineResponse);
  vi.mocked(adminApi.adminApi.retryDocument).mockResolvedValue({ requeued: 1, action: "retry" });
  vi.mocked(adminApi.adminApi.reprocessDocument).mockResolvedValue({ requeued: 1, action: "reprocess" });
  vi.mocked(adminApi.adminApi.reocrDocument).mockResolvedValue({ requeued: 0, action: "reocr" });
  vi.mocked(adminApi.adminApi.retranslateDocument).mockResolvedValue({ requeued: 0, action: "retranslate" });
  vi.mocked(adminApi.adminApi.reembedDocument).mockResolvedValue({ requeued: 1, action: "reembed" });
});

describe("AdminIngestionPage", () => {
  it("shows the Ingestion Pipeline heading", async () => {
    render(<AdminIngestionPage />);
    expect(
      await screen.findByRole("heading", { name: "Ingestion Pipeline" })
    ).toBeInTheDocument();
  });

  it("shows summary cards with counts", async () => {
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(2);
  });

  it("renders jobs table when jobs exist", async () => {
    render(<AdminIngestionPage />);
    expect(await screen.findByText("Test Document")).toBeInTheDocument();
    expect(screen.getByText("parse")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("Failed Doc")).toBeInTheDocument();
    expect(screen.getByText("vectorize")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("truncates long errors in table", async () => {
    const longError = "a".repeat(200);
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue({
      ...mockPopulatedResponse,
      jobs: [{ ...mockFailedJob, last_error: longError }],
    });
    render(<AdminIngestionPage />);
    await screen.findByText("Failed Doc");
    const truncated = "a".repeat(80) + "\u2026";
    expect(screen.getByText(truncated)).toBeInTheDocument();
  });

  it("shows empty state when no jobs", async () => {
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue(mockEmptyResponse);
    render(<AdminIngestionPage />);
    expect(await screen.findByText("No pipeline jobs")).toBeInTheDocument();
  });

  it("shows empty state with filter hint when filters are active", async () => {
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue(mockEmptyResponse);
    render(<AdminIngestionPage />);
    await screen.findByText("No pipeline jobs");
    const sourceInput = screen.getByPlaceholderText("Filter by source ID");
    await userEvent.type(sourceInput, "abc");
    expect(await screen.findByText(/Try clearing them/)).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockRejectedValue(
      new Error("Failed to fetch ingestion status")
    );
    render(<AdminIngestionPage />);
    expect(
      await screen.findByText("Failed to fetch ingestion status")
    ).toBeInTheDocument();
  });

  it("calls getIngestionStatus with status filter", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const select = screen.getByLabelText("Status");
    await user.selectOptions(select, "failed");

    await waitFor(() => {
      expect(vi.mocked(adminApi.adminApi.getIngestionStatus)).toHaveBeenCalledWith(
        expect.objectContaining({ status: "failed" })
      );
    });
  });

  it("calls getIngestionStatus with source_id filter", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const input = screen.getByPlaceholderText("Filter by source ID");
    await user.type(input, "src-1");

    await waitFor(() => {
      expect(vi.mocked(adminApi.adminApi.getIngestionStatus)).toHaveBeenCalledWith(
        expect.objectContaining({ source_id: "src-1" })
      );
    });
  });

  it("calls getIngestionStatus with since filter", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const sinceInput = screen.getByLabelText("Since");
    await user.type(sinceInput, "2026-01-01");

    await waitFor(() => {
      expect(vi.mocked(adminApi.adminApi.getIngestionStatus)).toHaveBeenCalledWith(
        expect.objectContaining({ since: "2026-01-01" })
      );
    });
  });

  it("shows clear filters button and clears filters on click", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue(mockEmptyResponse);
    render(<AdminIngestionPage />);
    await screen.findByText("No pipeline jobs");

    const input = screen.getByPlaceholderText("Filter by source ID");
    await user.type(input, "abc");

    const clearBtn = await screen.findByText("Clear filters");
    expect(clearBtn).toBeInTheDocument();

    await user.click(clearBtn);
    expect(input).toHaveValue("");
  });

  it("expands row and loads document timeline", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const expandBtn = screen.getAllByRole("button", { name: "Expand trace" })[0];
    await user.click(expandBtn);

    expect(
      await screen.findByText("Processing timeline — Test Document")
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Source: Test Source")
    ).toBeInTheDocument();
  });

  it("shows 404 message when document timeline returns 404", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.getDocumentTimeline).mockRejectedValue(
      new Error("404: Not found")
    );
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const expandBtn = screen.getAllByRole("button", { name: "Expand trace" })[0];
    await user.click(expandBtn);

    expect(
      await screen.findByText("No pipeline timeline found for this document.")
    ).toBeInTheDocument();
  });

  it("pagination shows page info and navigates", async () => {
    const manyJobs = Array.from({ length: 30 }).map((_, i) => ({
      ...mockJob,
      id: `job-${i}`,
      document_id: `doc-${i}`,
      document_title: `Doc ${i}`,
    }));
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue({
      jobs: manyJobs.slice(0, 25),
      total: 30,
      summary: { pending: 0, running: 0, completed: 30, failed: 0 },
    });

    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Doc 0");
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();

    await user.click(screen.getByText("Next"));
    await waitFor(() => {
      expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
    });
  });

  it("shows no pipeline jobs when data has empty jobs array", async () => {
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue(mockEmptyResponse);
    render(<AdminIngestionPage />);
    expect(await screen.findByText("No pipeline jobs")).toBeInTheDocument();
  });

  it("renders summary zero values when summary is empty", async () => {
    vi.mocked(adminApi.adminApi.getIngestionStatus).mockResolvedValue({
      ...mockEmptyResponse,
      summary: {},
    });
    render(<AdminIngestionPage />);
    await screen.findByText("No pipeline jobs");
    expect(screen.getAllByText("0").length).toBe(4);
  });

  it("shows retry actions when timeline has failed stages", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const expandBtn = screen.getAllByRole("button", { name: "Expand trace" })[0];
    await user.click(expandBtn);
    await screen.findByText("Processing timeline — Test Document");

    // Retry actions section should appear because there's a failed stage
    expect(await screen.findByText("Retry actions")).toBeInTheDocument();
    expect(screen.getByText("Retry failed stage")).toBeInTheDocument();
  });

  it("retry button calls retryDocument and shows success toast", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const expandBtn = screen.getAllByRole("button", { name: "Expand trace" })[0];
    await user.click(expandBtn);
    await screen.findByText("Processing timeline — Test Document");

    // Click "Retry failed stage" button
    const retryBtn = screen.getByRole("button", { name: /Retry failed stage/i });
    await user.click(retryBtn);

    // Confirmation dialog appears
    expect(await screen.findByText(/Retry failed stage for this document\?/i)).toBeInTheDocument();

    // Click Confirm
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(vi.mocked(adminApi.adminApi.retryDocument)).toHaveBeenCalledWith("doc-1");
    expect(await screen.findByText(/retry: requeued 1 job/i)).toBeInTheDocument();
  });

  it("cancel button dismisses confirmation dialog", async () => {
    const user = userEvent.setup();
    render(<AdminIngestionPage />);
    await screen.findByText("Test Document");

    const expandBtn = screen.getAllByRole("button", { name: "Expand trace" })[0];
    await user.click(expandBtn);
    await screen.findByText("Processing timeline — Test Document");

    const retryBtn = screen.getByRole("button", { name: /Retry failed stage/i });
    await user.click(retryBtn);

    expect(await screen.findByText(/Retry failed stage for this document\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/Retry failed stage for this document\?/i)).not.toBeInTheDocument();
  });
});
