import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { ChatCitationCard } from "./ChatCitationCard";
import type { DocumentChatCitation, RetrievalTrace } from "@/api/chat";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    params,
    search,
    onClick,
    target,
  }: {
    children: React.ReactNode;
    params?: Record<string, string>;
    search?: Record<string, string | undefined>;
    onClick?: (e: React.MouseEvent) => void;
    target?: string;
  }) => {
    const docId = params?.docId ?? "";
    const href = `/doc/${docId}?page=${search?.page ?? ""}&chunk=${search?.chunk ?? ""}`;
    return <a href={href} onClick={onClick} target={target}>{children}</a>;
  },
}));

function makeCitation(
  overrides: Partial<DocumentChatCitation> = {},
): DocumentChatCitation {
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

describe("ChatCitationCard", () => {
  it("renders title and excerpt", () => {
    render(
      <ul>
        <ChatCitationCard citation={makeCitation()} index={0} />
      </ul>,
    );
    expect(screen.getByText("Contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("some text excerpt")).toBeInTheDocument();
  });

  it("shows index badge", () => {
    render(
      <ul>
        <ChatCitationCard citation={makeCitation()} index={2} />
      </ul>,
    );
    expect(screen.getByText("[3]")).toBeInTheDocument();
  });

  it("displays page_number and section_heading when present", () => {
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ page_number: 4, section_heading: "Section 8 — Termination" })}
          index={0}
        />
      </ul>,
    );
    expect(screen.getByText(/p\. 4/)).toBeInTheDocument();
    expect(screen.getByText(/Section 8 — Termination/)).toBeInTheDocument();
  });

  it("does not crash without page_number or section_heading", () => {
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ page_number: null, section_heading: null })}
          index={0}
        />
      </ul>,
    );
    expect(screen.getByText("Contract.pdf")).toBeInTheDocument();
  });

  it("shows translated indicator when translated_from is set", () => {
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ translated_from: "he" })}
          index={0}
        />
      </ul>,
    );
    expect(screen.getByText(/Translated from he/)).toBeInTheDocument();
  });

  it("renders open link to document viewer", () => {
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ page_number: 5, chunk_index: 2 })}
          index={0}
        />
      </ul>,
    );
    const link = screen.getByRole("link", { name: "Open document" });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toContain("/doc/doc-1");
  });

  it("falls back to untitled document when no title", () => {
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ doc_title: null, document_title: null })}
          index={0}
        />
      </ul>,
    );
    expect(screen.getByText(/Untitled/i)).toBeInTheDocument();
  });

  it("calls onOpenCitation when card is clicked", () => {
    const onOpen = vi.fn();
    const citation = makeCitation({ citation_id: "cit-click" });
    render(
      <ul>
        <ChatCitationCard citation={citation} index={0} onOpenCitation={onOpen} />
      </ul>,
    );
    const card = screen.getByRole("button", { name: "Contract.pdf" });
    fireEvent.click(card);
    expect(onOpen).toHaveBeenCalledWith(citation, undefined);
  });

  it("calls onOpenCitation on Enter key", () => {
    const onOpen = vi.fn();
    const citation = makeCitation({ citation_id: "cit-keyboard" });
    render(
      <ul>
        <ChatCitationCard citation={citation} index={0} onOpenCitation={onOpen} />
      </ul>,
    );
    const card = screen.getByRole("button", { name: "Contract.pdf" });
    fireEvent.keyDown(card, { key: "Enter" });
    expect(onOpen).toHaveBeenCalledWith(citation, undefined);
  });

  it("calls onOpenCitation on Space key", () => {
    const onOpen = vi.fn();
    const citation = makeCitation({ citation_id: "cit-space" });
    render(
      <ul>
        <ChatCitationCard citation={citation} index={0} onOpenCitation={onOpen} />
      </ul>,
    );
    const card = screen.getByRole("button", { name: "Contract.pdf" });
    fireEvent.keyDown(card, { key: " " });
    expect(onOpen).toHaveBeenCalledWith(citation, undefined);
  });

  it("stops propagation on Open link click so card click is not triggered", () => {
    const onOpen = vi.fn();
    render(
      <ul>
        <ChatCitationCard
          citation={makeCitation({ citation_id: "cit-stop" })}
          index={0}
          onOpenCitation={onOpen}
        />
      </ul>,
    );
    const link = screen.getByRole("link", { name: "Open document" });
    fireEvent.click(link);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("does not make the card a button when onOpenCitation is not provided", () => {
    render(
      <ul>
        <ChatCitationCard citation={makeCitation()} index={0} />
      </ul>,
    );
    // The card itself is not a button; only the Save action is.
    expect(screen.queryByRole("button", { name: "Contract.pdf" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save to evidence pack/ })).toBeInTheDocument();
  });

  it("forwards trace to onOpenCitation when trace prop is provided", () => {
    const onOpen = vi.fn();
    const citation = makeCitation({ citation_id: "cit-trace" });
    const trace: RetrievalTrace = {
      stages: [{ stage: "vector", candidate_count: 5, timing_ms: 10.0, description: null }],
      candidates: [],
      reranker_enabled: false,
      total_latency_ms: 10.0,
    };

    render(
      <ul>
        <ChatCitationCard citation={citation} index={0} trace={trace} onOpenCitation={onOpen} />
      </ul>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Contract.pdf" }));
    expect(onOpen).toHaveBeenCalledWith(citation, trace);
  });
});
