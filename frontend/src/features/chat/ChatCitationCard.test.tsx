import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { ChatCitationCard } from "./ChatCitationCard";
import type { DocumentChatCitation } from "@/api/chat";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    params,
    search,
  }: {
    children: React.ReactNode;
    params?: Record<string, string>;
    search?: Record<string, string | undefined>;
  }) => {
    const docId = params?.docId ?? "";
    const href = `/doc/${docId}?page=${search?.page ?? ""}&chunk=${search?.chunk ?? ""}`;
    return <a href={href}>{children}</a>;
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
    const link = screen.getByRole("link", { name: "Open" });
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
});
