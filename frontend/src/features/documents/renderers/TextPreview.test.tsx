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
