import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { PdfViewer } from "./PdfViewer";

// Mock worker URL — Vite resolves ?url at build time; provide a stub for tests
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "" }));

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: vi.fn(),
}));

import { getDocument } from "pdfjs-dist";
const mockGetDocument = getDocument as ReturnType<typeof vi.fn>;

function makeMockPage(text = "sample pdf text") {
  return {
    getViewport: vi.fn().mockReturnValue({ width: 600, height: 800 }),
    render: vi.fn().mockReturnValue({ promise: Promise.resolve() }),
    getTextContent: vi.fn().mockResolvedValue({ items: [{ str: text }] }),
  };
}

function makeMockTask({ numPages = 3, fail = false } = {}) {
  const mockPage = makeMockPage();
  const promise = fail
    ? Promise.reject(new Error("load failed"))
    : Promise.resolve({ numPages, getPage: vi.fn().mockResolvedValue(mockPage) });
  return { promise, destroy: vi.fn(), _mockPage: mockPage };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PdfViewer", () => {
  it("shows loading state initially", () => {
    // Never-resolving promise to keep loading state
    const neverTask = { promise: new Promise(() => {}), destroy: vi.fn() };
    mockGetDocument.mockReturnValue(neverTask);
    render(<PdfViewer docId="doc-1" />);
    expect(screen.getByText("Loading PDF…")).toBeInTheDocument();
  });

  it("calls getDocument with the correct download URL", async () => {
    const task = makeMockTask();
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-abc" />);
    expect(mockGetDocument).toHaveBeenCalledWith("/api/download/doc-abc");
  });

  it("shows page count after successful load", async () => {
    const task = makeMockTask({ numPages: 5 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => expect(screen.getByText("1 / 5")).toBeInTheDocument());
  });

  it("next page button increments page number", async () => {
    const user = userEvent.setup();
    const task = makeMockTask({ numPages: 3 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 3"));
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("previous page button decrements page number", async () => {
    const user = userEvent.setup();
    const task = makeMockTask({ numPages: 3 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 3"));
    await user.click(screen.getByRole("button", { name: "Next page" }));
    await user.click(screen.getByRole("button", { name: "Previous page" }));
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("previous page is disabled on first page", async () => {
    const task = makeMockTask({ numPages: 3 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 3"));
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("next page is disabled on last page", async () => {
    const user = userEvent.setup();
    const task = makeMockTask({ numPages: 2 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 2"));
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("zoom buttons are present with accessible labels", async () => {
    const task = makeMockTask();
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 3"));
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset zoom" })).toBeInTheDocument();
  });

  it("clicking zoom in triggers a re-render (getPage called again)", async () => {
    const user = userEvent.setup();
    const getPageMock = vi.fn().mockResolvedValue(makeMockPage());
    const task = {
      promise: Promise.resolve({ numPages: 1, getPage: getPageMock }),
      destroy: vi.fn(),
    };
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 1"));
    const callsBefore = getPageMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(getPageMock.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("zoom out is disabled when at minimum scale after repeated clicks", async () => {
    const user = userEvent.setup();
    const task = makeMockTask({ numPages: 1 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 1"));
    // Click zoom out until disabled (default 1.2, min 0.5 → 3 clicks: 0.95, 0.70, 0.45 → capped at 0.5)
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    for (let i = 0; i < 5; i++) {
      if (!zoomOut.hasAttribute("disabled")) await user.click(zoomOut);
    }
    expect(zoomOut).toBeDisabled();
  });

  it("reset zoom re-enables zoom out after it was disabled", async () => {
    const user = userEvent.setup();
    const task = makeMockTask({ numPages: 1 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 1"));
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    for (let i = 0; i < 5; i++) {
      if (!zoomOut.hasAttribute("disabled")) await user.click(zoomOut);
    }
    await user.click(screen.getByRole("button", { name: "Reset zoom" }));
    expect(zoomOut).not.toBeDisabled();
  });

  it("shows graceful fallback on PDF load failure", async () => {
    const task = makeMockTask({ fail: true });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() =>
      expect(screen.getByText("Text extraction failed")).toBeInTheDocument()
    );
  });

  it("page area has an accessible label", async () => {
    const task = makeMockTask({ numPages: 4 });
    mockGetDocument.mockReturnValue(task);
    render(<PdfViewer docId="doc-1" />);
    await waitFor(() => screen.getByText("1 / 4"));
    expect(screen.getByRole("document", { name: /PDF page 1 of 4/i })).toBeInTheDocument();
  });

  it("reports match count via onMatchCountChange when searchQuery matches text", async () => {
    const getPageMock = vi.fn().mockResolvedValue(
      makeMockPage("hello world hello again")
    );
    const task = {
      promise: Promise.resolve({ numPages: 1, getPage: getPageMock }),
      destroy: vi.fn(),
    };
    mockGetDocument.mockReturnValue(task);
    const onMatchCountChange = vi.fn();
    render(<PdfViewer docId="doc-1" searchQuery="hello" onMatchCountChange={onMatchCountChange} />);
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(2);
    });
  });

  it("reports zero matches when searchQuery does not match", async () => {
    const getPageMock = vi.fn().mockResolvedValue(makeMockPage("hello world"));
    const task = {
      promise: Promise.resolve({ numPages: 1, getPage: getPageMock }),
      destroy: vi.fn(),
    };
    mockGetDocument.mockReturnValue(task);
    const onMatchCountChange = vi.fn();
    render(<PdfViewer docId="doc-1" searchQuery="notfound" onMatchCountChange={onMatchCountChange} />);
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(0);
    });
  });

  it("navigates to page containing active match when activeSearchIndex changes", async () => {
    const page1 = makeMockPage("cat toy");
    const page2 = makeMockPage("dog bone");
    const page3 = makeMockPage("cat nip");
    const pageMap: Record<number, typeof page1> = { 1: page1, 2: page2, 3: page3 };
    const getPageMock = vi.fn().mockImplementation((n: number) =>
      Promise.resolve(pageMap[n] ?? page1)
    );
    const task = {
      promise: Promise.resolve({ numPages: 3, getPage: getPageMock }),
      destroy: vi.fn(),
    };
    mockGetDocument.mockReturnValue(task);
    const { rerender } = render(<PdfViewer docId="doc-1" searchQuery="cat" />);
    await waitFor(() => expect(screen.getByText("1 / 3")).toBeInTheDocument());

    rerender(<PdfViewer docId="doc-1" searchQuery="cat" activeSearchIndex={0} />);
    await waitFor(() => expect(screen.getByText("1 / 3")).toBeInTheDocument());

    rerender(<PdfViewer docId="doc-1" searchQuery="cat" activeSearchIndex={1} />);
    await waitFor(() => expect(screen.getByText("3 / 3")).toBeInTheDocument());
  });
});
