import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { CitationCard } from "./CitationCard";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, string>;
    search?: Record<string, string>;
  }) => <a href={`${to}/${params?.docId ?? ""}`}>{children}</a>,
}));

const mockCitation = {
  citation_id: "cit-1",
  document_id: "doc-1",
  doc_title: "Vendor Risk Assessment",
  chunk_text: "This document covers vendor risk management.",
  score: 0.92,
  chunk_index: 0,
  source_id: null,
};

describe("CitationCard", () => {
  it("renders document title as link", () => {
    render(
      <ul>
        <CitationCard citation={mockCitation} />
      </ul>
    );
    expect(
      screen.getByRole("link", { name: "Vendor Risk Assessment" })
    ).toBeInTheDocument();
  });

  it("renders chunk text", () => {
    render(
      <ul>
        <CitationCard citation={mockCitation} />
      </ul>
    );
    expect(
      screen.getByText("This document covers vendor risk management.")
    ).toBeInTheDocument();
  });

  it("shows relevance score", () => {
    render(
      <ul>
        <CitationCard citation={mockCitation} />
      </ul>
    );
    expect(screen.getByText("Relevance: 92%")).toBeInTheDocument();
  });

  it("falls back to document_id when no title", () => {
    render(
      <ul>
        <CitationCard citation={{ ...mockCitation, doc_title: "" }} />
      </ul>
    );
    expect(screen.getByRole("link", { name: "doc-1" })).toBeInTheDocument();
  });
});
