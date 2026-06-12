import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import { render } from "@/test/render";
import { SearchPage } from "./SearchPage";
import * as searchApi from "@/api/search";
import type { SearchFilters } from "@/api/search";
import { getPreview } from "@/api/documents";

const routerMocks = vi.hoisted(() => ({
  useSearch: vi.fn(() => ({ q: "", mode: "hybrid" })),
}));

const navigateMock = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useSearch: routerMocks.useSearch,
  useNavigate: () => navigateMock,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("@/api/search");
vi.mock("@/api/documents", () => ({
  getPreview: vi.fn(() => Promise.resolve({ document_id: "doc-1" })),
}));

const mockResults = [
  {
    document_id: "doc-1",
    source_id: "src-1",
    external_id: null,
    title: "Annual Report 2024",
    snippet: "Revenue grew 12% year-over-year.",
    source: "folder",
    source_label: "Folder",
    mime_type: "application/pdf",
    tags: [],
    translation_quality: null,
    translation_score: 0,
    score: 0.9,
    updated_at: new Date().toISOString(),
    indexed_at: new Date().toISOString(),
    why: [],
  },
] satisfies searchApi.SearchResult[];

beforeEach(() => {
  vi.clearAllMocks();
  routerMocks.useSearch.mockReturnValue({ q: "", mode: "hybrid" });
  navigateMock.mockClear();
  vi.mocked(searchApi.search).mockResolvedValue({
    results: mockResults,
    total: 1,
    query: "annual",
  });
  vi.mocked(getPreview).mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SearchPage — debounce", () => {
  it("does not call the search API before the debounce delay elapses", () => {
    vi.useFakeTimers();
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });

    // No API call before the timer fires
    expect(searchApi.search).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("calls the search API automatically after 350 ms without an explicit submit", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    await waitFor(() => {
      expect(searchApi.search).toHaveBeenCalledWith("annual", "hybrid", {}, 1);
    });
    vi.useRealTimers();
  });

  it("debounces: only fires once when the user types quickly", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<SearchPage />);

    // Simulate rapid typing
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "a" },
    });
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "an" },
    });
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "ann" },
    });
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    await waitFor(() => {
      expect(searchApi.search).toHaveBeenCalledTimes(1);
      expect(searchApi.search).toHaveBeenCalledWith("annual", "hybrid", {}, 1);
    });
    vi.useRealTimers();
  });

  it("does not trigger debounce for input shorter than 2 characters", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "a" },
    });

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    expect(searchApi.search).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("updates the URL with replace: true on debounce", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({ replace: true }),
      );
    });
    vi.useRealTimers();
  });
});

describe("SearchPage — filter integration", () => {
  it("passes file_type filter from FilterPanel to the search API", async () => {
    render(<SearchPage />);

    // Submit a query first so the results area is visible
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText("Annual Report 2024")).toBeInTheDocument(),
    );

    // Open advanced filters and check PDF filter
    const pdfCheckbox = screen.getByRole("checkbox", { name: /pdf/i });
    fireEvent.click(pdfCheckbox);

    await waitFor(() => {
      const calls = vi.mocked(searchApi.search).mock.calls;
      const lastCall = calls[calls.length - 1];
      const filters = lastCall[2] as SearchFilters;
      expect(filters.file_type).toEqual(
        expect.arrayContaining(["application/pdf"]),
      );
    });
  });

  it("shows a filter chip for an active file_type filter", async () => {
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText("Annual Report 2024")).toBeInTheDocument(),
    );

    const pdfCheckbox = screen.getByRole("checkbox", { name: /pdf/i });
    fireEvent.click(pdfCheckbox);

    await waitFor(() => {
      // The chip label is the last segment of the mime type ("pdf")
      expect(screen.getByLabelText(/remove filter.*pdf/i)).toBeInTheDocument();
    });
  });

  it("removes the filter when the chip's remove button is clicked", async () => {
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText("Annual Report 2024")).toBeInTheDocument(),
    );

    const pdfCheckbox = screen.getByRole("checkbox", { name: /pdf/i });
    fireEvent.click(pdfCheckbox);

    const removeBtn = await screen.findByLabelText(/remove filter.*pdf/i);
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(screen.queryByLabelText(/remove filter.*pdf/i)).not.toBeInTheDocument();
    });
  });

  it("sends mode change to the search API when a mode button is clicked", async () => {
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText("Annual Report 2024")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Keyword" }));

    await waitFor(() => {
      const calls = vi.mocked(searchApi.search).mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall[1]).toBe("keyword");
    });
  });

  it("shows retrieval-degraded chip when the API signals retrieval_degraded", async () => {
    vi.mocked(searchApi.search).mockResolvedValueOnce({
      results: mockResults,
      total: 1,
      query: "annual",
      retrieval_degraded: true,
    });

    render(<SearchPage />);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "annual" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(
        screen.getByText("Search degraded — partial results"),
      ).toBeInTheDocument();
    });
  });
});
