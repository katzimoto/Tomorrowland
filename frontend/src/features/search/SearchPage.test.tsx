import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { SearchPage } from "./SearchPage";
import * as searchApi from "@/api/search";
import {
  clearPerformanceTelemetryEvents,
  getPerformanceTelemetryEvents,
} from "@/lib/performanceTelemetry";

// Mock TanStack Router hooks
vi.mock("@tanstack/react-router", () => ({
  useSearch: () => ({ q: "", mode: "hybrid" }),
  useNavigate: () => vi.fn(),
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
  vi.mocked(searchApi.search).mockResolvedValue({
    results: mockResults,
    total: 1,
    query: "vendor risk",
  });
});

describe("SearchPage", () => {
  it("renders the search input and title", () => {
    render(<SearchPage />);
    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument();
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("shows mode buttons", () => {
    render(<SearchPage />);
    expect(screen.getByRole("button", { name: "Hybrid" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keyword" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Semantic" }),
    ).toBeInTheDocument();
  });

  it("shows empty start state before any query", () => {
    render(<SearchPage />);
    expect(screen.getByText("Start searching")).toBeInTheDocument();
  });

  it("shows results after search is submitted", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "vendor risk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(
        screen.getByText("Vendor Risk Assessment 2024"),
      ).toBeInTheDocument();
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
