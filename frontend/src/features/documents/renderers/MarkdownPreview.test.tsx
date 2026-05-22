import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { MarkdownPreview } from "./MarkdownPreview";

vi.mock("@/api/documents", () => ({
  getDocumentText: vi.fn(),
}));

import { getDocumentText } from "@/api/documents";
const mockGetDocumentText = getDocumentText as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MarkdownPreview", () => {
  it("shows loading state while fetching", () => {
    mockGetDocumentText.mockReturnValue(new Promise(() => {}));
    render(<MarkdownPreview docId="doc-1" />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders markdown as formatted HTML after fetch", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello\n\nThis is **bold** text.",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 30,
    });
    const { container } = render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(container.querySelector("h1")).toHaveTextContent("Hello");
    });
    expect(container.querySelector("strong")).toHaveTextContent("bold");
  });

  it("renders code blocks", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "```js\nconst x = 1;\n```",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 20,
    });
    const { container } = render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(container.querySelector("code")).toHaveTextContent("const x = 1;");
    });
  });

  it("toggles to raw mode and shows raw text", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 7,
    });
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => screen.getByText("Raw"));
    fireEvent.click(screen.getByText("Raw"));
    expect(screen.getByText("# Hello")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("toggles back to rendered mode", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 7,
    });
    const { container } = render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => screen.getByText("Raw"));
    fireEvent.click(screen.getByText("Raw"));
    fireEvent.click(screen.getByText("Rendered"));
    await waitFor(() => {
      expect(container.querySelector("h1")).toHaveTextContent("Hello");
    });
  });

  it("strips <script> tags from rendered output", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: 'Hello <script>alert("xss")</script>',
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 35,
    });
    const { container } = render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(container.querySelector("script")).not.toBeInTheDocument();
    });
    expect(container.querySelector("p")).toHaveTextContent("Hello");
  });

  it("shows Raw button as active when in raw mode", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 7,
    });
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => screen.getByText("Raw"));
    fireEvent.click(screen.getByText("Raw"));
    expect(screen.getByText("Raw")).toHaveClass(/Active/);
  });

  it("shows Rendered button as active in default mode", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 7,
    });
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => screen.getByText("Rendered"));
    expect(screen.getByText("Rendered")).toHaveClass(/Active/);
  });

  it("shows no content message when text is empty", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 0,
    });
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(screen.getByText("No content")).toBeInTheDocument();
    });
  });

  it("shows error message when fetch fails and no fallback", async () => {
    mockGetDocumentText.mockRejectedValue(new Error("Network error"));
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(screen.getByText("Failed to load document content.")).toBeInTheDocument();
    });
  });

  it("uses fallbackText when fetch fails", async () => {
    mockGetDocumentText.mockRejectedValue(new Error("Network error"));
    const { container } = render(<MarkdownPreview docId="doc-1" fallbackText="# Fallback" />);
    await waitFor(() => {
      expect(container.querySelector("h1")).toHaveTextContent("Fallback");
    });
  });

  it("renders a Copy button", async () => {
    mockGetDocumentText.mockResolvedValue({
      text: "# Hello",
      truncated: false,
      offset: 0,
      limit: 100000,
      total_length: 7,
    });
    render(<MarkdownPreview docId="doc-1" />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /copy raw markdown/i })).toBeInTheDocument();
    });
  });
});
