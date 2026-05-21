import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import * as documentsApi from "@/api/documents";

vi.mock("@/api/documents", () => ({
  getDocumentText: vi.fn(),
  getDownloadUrl: vi.fn().mockReturnValue("/api/download/doc-1"),
  getPreview: vi.fn(),
  getTranslationVersions: vi.fn(),
}));

vi.mock("highlight.js/lib/core", () => ({
  default: {
    registerLanguage: vi.fn(),
    highlight: vi.fn().mockImplementation((text: string) => ({
      value: `<span class="hljs-mock">${text}</span>`,
    })),
  },
}));

// Language imports mocked to prevent the module-level hljs.registerLanguage calls
vi.mock("highlight.js/lib/languages/json", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/xml", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/yaml", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/python", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/javascript", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/typescript", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/bash", () => ({ default: {} }));
vi.mock("highlight.js/lib/languages/sql", () => ({ default: {} }));
vi.mock("highlight.js/styles/github.min.css", () => ({}));

// Import after mocks
const { CodeViewer } = await import("./CodeViewer");

beforeEach(() => {
  vi.mocked(documentsApi.getDocumentText).mockResolvedValue({
    text: 'const x = 1;\nconst y = 2;\n',
    truncated: false,
    offset: 0,
    limit: 50_000,
  });
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("CodeViewer", () => {
  it("shows loading state initially", () => {
    vi.mocked(documentsApi.getDocumentText).mockReturnValue(new Promise(() => {}));
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders highlighted output after fetch", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      expect(document.querySelector(".hljs-mock")).toBeInTheDocument();
    });
  });

  it("shows language label in toolbar", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      expect(screen.getByText(/json/i)).toBeInTheDocument();
    });
  });

  it("shows line count in toolbar", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      // 3 lines: "const x = 1;", "const y = 2;", "" (trailing newline)
      expect(screen.getByText(/3 lines/)).toBeInTheDocument();
    });
  });

  it("renders line numbers in gutter", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("gutter has aria-hidden", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      const gutter = document.querySelector("[aria-hidden='true']");
      expect(gutter).toBeInTheDocument();
    });
  });

  it("copy button has aria-label='Copy code'", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    });
  });

  it("copy button calls navigator.clipboard.writeText with full text", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByRole("button", { name: "Copy code" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('const x = 1;\nconst y = 2;\n');
  });

  it("Raw toggle switches to plain text (no hljs spans)", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByRole("button", { name: /raw/i }));
    fireEvent.click(screen.getByRole("button", { name: /raw/i }));
    expect(document.querySelector(".hljs-mock")).not.toBeInTheDocument();
    expect(screen.getByText(/const x = 1/)).toBeInTheDocument();
  });

  it("Raw toggle button shows active state when toggled", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByRole("button", { name: /raw/i }));
    fireEvent.click(screen.getByRole("button", { name: /raw/i }));
    const rawBtn = screen.getByRole("button", { name: /raw/i });
    expect(rawBtn.className).toMatch(/_btnActive/);
  });

  it("shows truncation notice when text is truncated", async () => {
    vi.mocked(documentsApi.getDocumentText).mockResolvedValue({
      text: "x".repeat(50_000),
      truncated: true,
      offset: 0,
      limit: 50_000,
    });
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => {
      expect(screen.getByText(/Showing first 50,000 characters/)).toBeInTheDocument();
    });
  });

  it("does not show truncation notice when text is not truncated", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByText(/json/i));
    expect(screen.queryByText(/Showing first 50,000 characters/)).not.toBeInTheDocument();
  });

  it("detects xml language from text/xml mime", async () => {
    render(<CodeViewer docId="doc-1" mimeType="text/xml" />);
    await waitFor(() => {
      expect(screen.getByText(/xml/i)).toBeInTheDocument();
    });
  });

  it("detects yaml language from application/x-yaml mime", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/x-yaml" />);
    await waitFor(() => {
      expect(screen.getByText(/yaml/i)).toBeInTheDocument();
    });
  });

  it("falls back to plaintext for unknown MIME type (no hljs spans)", async () => {
    render(<CodeViewer docId="doc-1" mimeType="text/x-unknown" />);
    await waitFor(() => screen.getByText(/plaintext/i));
    // plaintext skips hljs
    expect(document.querySelector(".hljs-mock")).not.toBeInTheDocument();
  });

  it("detects language from file extension in title", async () => {
    render(<CodeViewer docId="doc-1" mimeType="text/plain" title="script.py" />);
    await waitFor(() => {
      expect(screen.getByText(/python/i)).toBeInTheDocument();
    });
  });

  it("container has role='region' with title in aria-label", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" title="data.json" />);
    await waitFor(() => screen.getByRole("region", { name: "Code: data.json" }));
    expect(screen.getByRole("region", { name: "Code: data.json" })).toBeInTheDocument();
  });

  it("fallback aria-label when no title", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByRole("region", { name: "Code viewer" }));
    expect(screen.getByRole("region", { name: "Code viewer" })).toBeInTheDocument();
  });

  it("Wrap toggle button is present", async () => {
    render(<CodeViewer docId="doc-1" mimeType="application/json" />);
    await waitFor(() => screen.getByRole("button", { name: /wrap/i }));
    expect(screen.getByRole("button", { name: /wrap/i })).toBeInTheDocument();
  });
});
