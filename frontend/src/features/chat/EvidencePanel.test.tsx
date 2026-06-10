import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { EvidencePanel } from "./EvidencePanel";
import type { DocumentChatCitation, RetrievalTrace } from "@/api/chat";
import * as documentsApi from "@/api/documents";
import { ApiError } from "@/api/client";
import * as citationFeedbackApi from "@/api/citationFeedback";

vi.mock("@/api/documents");
vi.mock("@/api/citationFeedback");

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

  it("does not show retrieval tab for non-admin (default)", () => {
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));

    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} isAdmin={false} />);

    expect(screen.queryByRole("tab", { name: "Retrieval" })).not.toBeInTheDocument();
  });

  it("shows retrieval tab for admin", () => {
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));

    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} isAdmin={true} />);

    expect(screen.getByRole("tab", { name: "Retrieval" })).toBeInTheDocument();
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

describe("EvidencePanel tab navigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));
  });

  it("renders Evidence tab as active by default", () => {
    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} />);

    const evidenceTab = screen.getByRole("tab", { name: "Evidence" });
    expect(evidenceTab).toHaveAttribute("aria-selected", "true");
  });

  it("clicking Source tab shows source content", () => {
    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Source" }));

    expect(screen.getByRole("tab", { name: "Source" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Score")).toBeInTheDocument();
  });

  it("clicking Actions tab shows copy and report buttons", () => {
    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Actions" }));

    expect(screen.getByText("Copy citation")).toBeInTheDocument();
    expect(screen.getByText("Report problem")).toBeInTheDocument();
  });
});

const SAMPLE_TRACE: RetrievalTrace = {
  stages: [{ stage: "vector", candidate_count: 10, timing_ms: 25.5, description: null }],
  candidates: [],
  reranker_enabled: false,
  total_latency_ms: 100.0,
};

describe("EvidencePanel retrieval trace tab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));
  });

  it("shows no trace message when retrievalTrace is absent", () => {
    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} isAdmin={true} />);

    fireEvent.click(screen.getByRole("tab", { name: "Retrieval" }));

    expect(
      screen.getByText("No retrieval trace available for this message."),
    ).toBeInTheDocument();
  });

  it("shows latency and stage data from the trace", () => {
    render(
      <EvidencePanel
        citation={makeCitation()}
        onClose={vi.fn()}
        isAdmin={true}
        retrievalTrace={SAMPLE_TRACE}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Retrieval" }));

    expect(screen.getByText("100 ms")).toBeInTheDocument();
    expect(screen.getByText("vector")).toBeInTheDocument();
    expect(screen.getByText("25.5")).toBeInTheDocument();
  });

  it("shows Reranked badge when reranker_enabled is true", () => {
    render(
      <EvidencePanel
        citation={makeCitation()}
        onClose={vi.fn()}
        isAdmin={true}
        retrievalTrace={{ ...SAMPLE_TRACE, reranker_enabled: true }}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Retrieval" }));

    expect(screen.getByText("Reranked")).toBeInTheDocument();
  });
});

describe("EvidencePanel feedback form", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(documentsApi.getPreview).mockReturnValue(new Promise(() => {}));
  });

  it("shows feedback form after clicking Report problem", () => {
    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Actions" }));
    fireEvent.click(screen.getByText("Report problem"));

    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
  });

  it("calls submitCitationFeedback with citation data on submit", async () => {
    vi.mocked(citationFeedbackApi.submitCitationFeedback).mockResolvedValue({ id: "fb-1", ok: true });

    const citation = makeCitation({ citation_id: "cit-test", document_id: "doc-test" });
    render(<EvidencePanel citation={citation} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Actions" }));
    fireEvent.click(screen.getByText("Report problem"));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(citationFeedbackApi.submitCitationFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          document_id: "doc-test",
          citation_id: "cit-test",
          feedback_type: "wrong_passage",
        }),
      );
    });
  });

  it("disables form while submission is pending", async () => {
    // Never resolves so mutation stays pending
    vi.mocked(citationFeedbackApi.submitCitationFeedback).mockReturnValue(new Promise(() => {}));

    render(<EvidencePanel citation={makeCitation()} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "Actions" }));
    fireEvent.click(screen.getByText("Report problem"));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    });
  });
});
