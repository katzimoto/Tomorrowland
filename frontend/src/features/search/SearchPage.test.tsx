import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { SearchPage } from "./SearchPage";
import * as searchApi from "@/api/search";
import {
  clearPerformanceTelemetryEvents,
  getPerformanceTelemetryEvents,
} from "@/lib/performanceTelemetry";
import { getPreview } from "@/api/documents";

const routerMocks = vi.hoisted(() => ({
  useSearch: vi.fn(() => ({ q: "", mode: "hybrid" })),
  navigate: vi.fn(),
}));

const navigateMock = vi.fn();

// Mock TanStack Router hooks
vi.mock("@tanstack/react-router", () => ({
  useSearch: routerMocks.useSearch,
  useNavigate: () => navigateMock,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("@/api/search");
vi.mock("@/api/documents", () => ({ getPreview: vi.fn(() => Promise.resolve({ doc_id: "doc-1" })) }));

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
  {
    doc_id: "doc-2",
    source_id: "src-1",
    external_id: null,
    title: "Supplier Security Notes",
    snippet: "Follow-up notes for supplier security reviews.",
    source: "folder",
    source_label: "Folder",
    mime_type: "text/plain",
    tags: ["security"],
    translation_quality: null,
    score: 0.81,
    updated_at: new Date().toISOString(),
    indexed_at: new Date().toISOString(),
    why: [],
  },
] satisfies searchApi.SearchResult[];

beforeEach(() => {
  clearPerformanceTelemetryEvents();
  routerMocks.useSearch.mockReturnValue({ q: "", mode: "hybrid" });
  navigateMock.mockClear();
  vi.mocked(searchApi.search).mockResolvedValue({
    results: mockResults,
    total: 2,
    query: "vendor risk",
  });
  vi.mocked(getPreview).mockClear();
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
    expect(navigateMock).toHaveBeenCalledWith({
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
      expect(screen.getByText("2 results")).toBeInTheDocument();
    });
  });

  it("keeps previous results visible while a new search refetches", async () => {
    vi.mocked(searchApi.search)
      .mockResolvedValueOnce({ results: mockResults, total: 1, query: "vendor risk" })
      .mockImplementationOnce(() => new Promise(() => undefined));

    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Vendor Risk Assessment 2024")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "supplier risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.getByText("Vendor Risk Assessment 2024")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Updating results");
  });

  it("prefetches document preview on result hover", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    const result = await screen.findByText("Vendor Risk Assessment 2024");
    fireEvent.mouseEnter(result.closest('[role="option"]')!);

    await waitFor(() => expect(getPreview).toHaveBeenCalledWith("doc-1"));
  });

  it("focuses the search input with the slash shortcut", async () => {
    const user = userEvent.setup();
    render(<SearchPage />);
    const searchBox = screen.getByRole("searchbox");
    searchBox.blur();

    await user.keyboard("/");

    expect(searchBox).toHaveFocus();
  });

  it("moves the accessible selected result with keyboard shortcuts", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Vendor Risk Assessment 2024");

    const results = screen.getByRole("listbox", { name: "Search results" });
    results.focus();
    fireEvent.keyDown(results, { key: "j" });

    expect(screen.getByRole("option", { name: /Supplier Security Notes/ })).toHaveAttribute("aria-selected", "true");
    expect(results).toHaveAttribute("aria-activedescendant", "search-result-doc-2");

    fireEvent.keyDown(results, { key: "ArrowUp" });

    expect(screen.getByRole("option", { name: /Vendor Risk Assessment 2024/ })).toHaveAttribute("aria-selected", "true");
  });

  it("opens the selected result with Enter", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Vendor Risk Assessment 2024");

    const results = screen.getByRole("listbox", { name: "Search results" });
    results.focus();
    fireEvent.keyDown(results, { key: "ArrowDown" });
    fireEvent.keyDown(results, { key: "Enter" });

    expect(navigateMock).toHaveBeenCalledWith({ to: "/doc/$docId", params: { docId: "doc-2" } });
  });

  it("opens quick preview with Space and closes it with Escape", async () => {
    render(<SearchPage />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor risk" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Vendor Risk Assessment 2024");

    const results = screen.getByRole("listbox", { name: "Search results" });
    results.focus();
    fireEvent.keyDown(results, { key: " " });

    expect(screen.getByRole("dialog", { name: "Vendor Risk Assessment 2024" })).toBeInTheDocument();

    fireEvent.keyDown(results, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(results).toHaveFocus());
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
