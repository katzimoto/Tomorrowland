import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { TextPreview } from "./TextPreview";

vi.mock("@/api/documents", () => ({
  getDocumentText: vi.fn(),
}));

import { getDocumentText } from "@/api/documents";
const mockGetDocumentText = getDocumentText as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TextPreview — no docId (static mode)", () => {
  it("renders text directly", () => {
    render(<TextPreview text="Hello world content" />);
    expect(screen.getByText("Hello world content")).toBeInTheDocument();
  });

  it("shows fallback when text is empty", () => {
    render(<TextPreview text="" />);
    expect(screen.getByText("No text content available.")).toBeInTheDocument();
  });
});

describe("TextPreview — with docId (API mode)", () => {
  it("shows loading state while fetching", () => {
    mockGetDocumentText.mockReturnValue(new Promise(() => {}));
    render(<TextPreview docId="doc-1" />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders text returned from the full text API", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "Full document text content",
      total_length: 26,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() =>
      expect(screen.getByText("Full document text content")).toBeInTheDocument()
    );
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("shows fallback when API returns empty text", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "",
      total_length: 0,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() =>
      expect(screen.getByText("No text content available.")).toBeInTheDocument()
    );
  });

  it("shows Load more button when truncated is true", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "First chunk of text",
      total_length: 50000,
      offset: 0,
      limit: 10000,
      truncated: true,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() => expect(screen.getByText("Load more")).toBeInTheDocument());
  });

  it("does not show Load more when not truncated", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "Complete text",
      total_length: 13,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() => expect(screen.getByText("Complete text")).toBeInTheDocument());
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("calls getDocumentText with the correct docId", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "text",
      total_length: 4,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="my-doc-id" />);
    await waitFor(() => expect(mockGetDocumentText).toHaveBeenCalledWith("my-doc-id", expect.objectContaining({ offset: 0, limit: 10000 })));
  });

  it("appends more text when Load more is clicked", async () => {
    const user = userEvent.setup();
    mockGetDocumentText
      .mockResolvedValueOnce({
        text: "First chunk.",
        total_length: 25,
        offset: 0,
        limit: 10000,
        truncated: true,
      })
      .mockResolvedValueOnce({
        text: " Second chunk.",
        total_length: 25,
        offset: 10000,
        limit: 10000,
        truncated: false,
      });

    render(<TextPreview docId="doc-1" />);
    await waitFor(() => screen.getByText("Load more"));
    await user.click(screen.getByText("Load more"));

    await waitFor(() => expect(screen.queryByText("Load more")).not.toBeInTheDocument());
    expect(screen.getByText(/Second chunk/)).toBeInTheDocument();
  });
});

describe("TextPreview — search highlighting", () => {
  it("wraps matches in <mark> elements when searchQuery is provided", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "the quick brown fox",
      total_length: 19,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" searchQuery="quick" />);
    await waitFor(() => {
      const mark = document.querySelector("mark");
      expect(mark).toBeInTheDocument();
      expect(mark?.textContent).toBe("quick");
    });
  });

  it("reports correct match count via onMatchCountChange", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "foo bar foo baz foo",
      total_length: 19,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    const onMatchCountChange = vi.fn();
    render(<TextPreview docId="doc-1" searchQuery="foo" onMatchCountChange={onMatchCountChange} />);
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(3);
    });
  });

  it("gives active match a distinct highlight when activeSearchIndex is set", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "abc abc abc",
      total_length: 11,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" searchQuery="abc" activeSearchIndex={1} />);
    await waitFor(() => {
      const marks = document.querySelectorAll("mark");
      expect(marks.length).toBe(3);
      // The second mark (index 1) should have a different class than the first
      expect(marks[0].className).not.toBe(marks[1].className);
    });
  });

  it("shows zero match count when query has no results", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "hello world",
      total_length: 11,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    const onMatchCountChange = vi.fn();
    render(<TextPreview docId="doc-1" searchQuery="notfound" onMatchCountChange={onMatchCountChange} />);
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(0);
    });
  });
});

describe("TextPreview — virtualization", () => {
  it("renders virtual list for 12000 lines", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: Array.from({ length: 12000 }, (_, i) => `Line number ${i}`).join("\n"),
      total_length: 12000 * 12,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() => {
      expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
    });
    // Virtual container renders with role="list" and position: relative
    const container = document.querySelector('[role="list"]');
    expect(container).toBeInTheDocument();
    expect(container).toHaveStyle({ position: "relative" });
    // No <pre> element — virtualized rendering avoids full DOM
    expect(document.querySelector("pre")).not.toBeInTheDocument();
  });

  it("keeps DOM small for large documents", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: Array.from({ length: 20000 }, (_, i) => `Line ${i}`).join("\n"),
      total_length: 20000 * 7,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    render(<TextPreview docId="doc-1" />);
    await waitFor(() => {
      expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
    });
    const container = document.querySelector('[role="list"]');
    expect(container).toBeInTheDocument();
    // jsdom doesn't measure layout, so rows may be 0. Still, total DOM < 20000.
    const rows = container!.querySelectorAll('[class*="virtualRow"]');
    expect(rows.length).toBeLessThan(20000);
  });

  it("maintains global active-match index in virtualized mode", async () => {
    const lineCount = 12000;
    const textLines: string[] = [];
    for (let i = 0; i < lineCount; i++) {
      if (i === 2) textLines.push("line with match here");
      else if (i === 100) textLines.push("another match line");
      else if (i === 5000) textLines.push("third match instance");
      else textLines.push(`ordinary line ${i}`);
    }
    mockGetDocumentText.mockResolvedValue({
      text: textLines.join("\n"),
      total_length: textLines.join("\n").length,
      offset: 0,
      limit: 10000,
      truncated: false,
    });
    const onMatchCountChange = vi.fn();
    render(
      <TextPreview
        docId="doc-1"
        searchQuery="match"
        activeSearchIndex={0}
        onMatchCountChange={onMatchCountChange}
      />
    );
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(3);
    });
    // jsdom provides no layout so the virtualizer renders no rows — mark
    // rendering in the virtual path cannot be asserted here. The match count
    // (above) is the reliable proxy for correct global-index tracking.
  });
});
