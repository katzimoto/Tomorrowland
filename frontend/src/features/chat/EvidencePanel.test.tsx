import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { EvidencePanel } from "./EvidencePanel";
import type { DocumentChatCitation } from "@/api/chat";
import * as documentsApi from "@/api/documents";
import { ApiError } from "@/api/client";

vi.mock("@/api/documents");

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
    search,
    target,
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, string>;
    search?: Record<string, string | undefined>;
    target?: string;
  }) => {
    const href = params?.docId
      ? `/doc/${params.docId}?page=${search?.page ?? ""}&chunk=${search?.chunk ?? ""}`
      : to;
    return <a href={href} target={target}>{children}</a>;
  },
}));

vi.mock("./PreviewWithHighlight", () => ({
  PreviewWithHighlight: ({ preview, citation }: { preview: { document_id: string }; citation: DocumentChatCitation }) => (
    <div data-testid="preview-with-highlight">
      Preview: {preview.document_id} / Cit: {citation.citation_id}
    </div>
  ),
}));

function makeCitation(overrides: Partial<DocumentChatCitation> = {}): DocumentChatCitation {
  return {
    citation_id: "cit-1",
    document_id: "doc-1",
    doc_title: "Contract.pdf",
    chunk_text: "some text excerpt",
    score: 0.9,
    chunk_index: 0,
    source_id: null,
    ...overrides,
  };
}

const SAMPLE_PREVIEW: documentsApi.DocumentPreview = {
  document_id: "doc-1",
  title: "Contract.pdf",
  mime_type: "application/pdf",
  translation_quality: null,
  translation_score: 0,
  metadata: {},
  snippet: "some text excerpt",
  view_count: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EvidencePanel", () => {
  it("shows loading state while preview is fetching", () => {
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));

    render(
      <EvidencePanel citation={makeCitation()} onClose={vi.fn()} />,
    );

    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("shows document not found error on 404", async () => {
    vi.mocked(documentsApi.getPreview).mockRejectedValue(
      new ApiError(404, "Not found"),
    );

    render(
      <EvidencePanel citation={makeCitation()} onClose={vi.fn()} />,
    );

    expect(await screen.findByText("Document not found.")).toBeInTheDocument();
  });

  it("shows access denied error on 403", async () => {
    vi.mocked(documentsApi.getPreview).mockRejectedValue(
      new ApiError(403, "Forbidden"),
    );

    render(
      <EvidencePanel citation={makeCitation()} onClose={vi.fn()} />,
    );

    expect(await screen.findByText("Access denied.")).toBeInTheDocument();
  });

  it("shows generic error on other failures", async () => {
    vi.mocked(documentsApi.getPreview).mockRejectedValue(new Error("network"));

    render(
      <EvidencePanel citation={makeCitation()} onClose={vi.fn()} />,
    );

    expect(await screen.findByText("No preview available.")).toBeInTheDocument();
  });

  it("renders citation title and location when preview loads", async () => {
    vi.mocked(documentsApi.getPreview).mockResolvedValue(SAMPLE_PREVIEW);

    render(
      <EvidencePanel
        citation={makeCitation({
          page_number: 3,
          section_heading: "Termination",
        })}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("Contract.pdf")).toBeInTheDocument();
    expect(screen.getByText(/p\. 3/)).toBeInTheDocument();
    expect(screen.getByText(/Termination/)).toBeInTheDocument();
  });

  it("renders excerpt text", async () => {
    vi.mocked(documentsApi.getPreview).mockResolvedValue(SAMPLE_PREVIEW);

    render(
      <EvidencePanel
        citation={makeCitation({ text_excerpt: "This is the excerpt." })}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("This is the excerpt.")).toBeInTheDocument();
  });

  it("renders PreviewWithHighlight when preview loads", async () => {
    vi.mocked(documentsApi.getPreview).mockResolvedValue(SAMPLE_PREVIEW);

    render(
      <EvidencePanel citation={makeCitation()} onClose={vi.fn()} />,
    );

    expect(await screen.findByTestId("preview-with-highlight")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", async () => {
    vi.mocked(documentsApi.getPreview).mockResolvedValue(SAMPLE_PREVIEW);
    const onClose = vi.fn();

    render(
      <EvidencePanel citation={makeCitation()} onClose={onClose} />,
    );

    const closeBtn = await screen.findByRole("button", { name: "Close" });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders preview even when excerpt and location are missing", async () => {
    vi.mocked(documentsApi.getPreview).mockResolvedValue(SAMPLE_PREVIEW);

    render(
      <EvidencePanel
        citation={makeCitation({
          page_number: null,
          section_heading: null,
          text_excerpt: undefined,
          chunk_text: undefined,
        })}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByTestId("preview-with-highlight")).toBeInTheDocument();
  });
});
