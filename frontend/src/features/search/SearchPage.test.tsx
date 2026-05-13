import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { SearchPage } from "./SearchPage";
import * as searchApi from "@/api/search";
import {
  clearPerformanceTelemetryEvents,
  getPerformanceTelemetryEvents,
} from "@/lib/performanceTelemetry";

const routerMocks = vi.hoisted(() => ({
  useSearch: vi.fn(() => ({ q: "", mode: "hybrid" })),
  navigate: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  useSearch: routerMocks.useSearch,
  useNavigate: () => routerMocks.navigate,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("@/api/search");

const mockResults = [
  {
    doc_id: "doc-1",
    source_id: "src-1",
    external_id: null,
    title: "Vendor Risk Assessment 2024",
    snippet: "This document covers the annual vendor risk assessment process.",
    source: "confluence",
    source_label: "Confluence",
    mime_type: "application/pdf",
    tags: ["risk", "vendor"],
    translation_quality: null,
    score: 0.92,
    updated_at: new Date().toISOString(),
    indexed_at: new Date().toISOString(),
    why: [{ kind: "term", label: 'Matched "vendor risk" in title' }],
  },
] satisfies searchApi.SearchResult[];

beforeEach(() => {
  clearPerformanceTelemetryEvents();
  routerMocks.useSearch.mockReturnValue({ q: "", mode: "hybrid" });
  routerMocks.navigate.mockClear();
  vi.mocked(searchApi.search).mockReset();
  vi.mocked(searchApi.search).mockResolvedValue({
    results: mockResults,
    total: 1,
    query: "vendor risk",
  });
});

describe("SearchPage", () => {
  it("binds route search params to the typed search route", () => {
    render(<SearchPage />);
    expect(routerMocks.useSearch).toHaveBeenCalledWith({ from: "/app/search" });
  });

  it("renders the search input and title", () => {
    render(<SearchPage />);
    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument();
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("shows mode buttons", () => {
    render(<SearchPage />);
    expect(screen.getByRole("button", { name: "Hybrid" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keyword" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Semantic" })).toBeInTheDocument();
  });

  it("shows empty start state before any query", () => {
    render(<SearchPage />);
    expect(screen.getByText("Start searching")).toBeInTheDocument();
  });

  it("calls the search API when the search button is clicked", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(searchApi.search).toHaveBeenCalledWith("vendor risk", "hybrid", {}, 20);
    });
    expect(routerMocks.navigate).toHaveBeenCalledWith({
      to: "/search",
      search: expect.any(Function),
    });
  });

  it("calls the search API when Enter is pressed in the input", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk" },
    });
    fireEvent.keyDown(screen.getByRole("searchbox"), {
      key: "Enter",
      code: "Enter",
    });

    await waitFor(() => {
      expect(searchApi.search).toHaveBeenCalledWith("vendor risk", "hybrid", {}, 20);
    });
  });

  it("shows results after search is submitted", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(screen.getByText("Vendor Risk Assessment 2024")).toBeInTheDocument();
    });
  });

  it("records privacy-safe search request and first-result timings", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk secret query" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      const events = getPerformanceTelemetryEvents();
      expect(events.map((event) => event.name)).toEqual(
        expect.arrayContaining(["search.request", "search.firstResult"]),
      );
      const serialized = JSON.stringify(events);
      expect(serialized).not.toContain("vendor risk secret query");
      expect(serialized).not.toContain("doc-1");
      expect(serialized).not.toContain("src-1");
    });
  });

  it("shows result count", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(screen.getByText("1 result")).toBeInTheDocument();
    });
  });

  it("shows empty state when no results", async () => {
    vi.mocked(searchApi.search).mockResolvedValueOnce({
      results: [],
      total: 0,
      query: "zzzzzz",
    });
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "zzzzzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(screen.getByText("No results found")).toBeInTheDocument();
    });
  });
});
