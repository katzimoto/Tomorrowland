import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { ParentContextBanner } from "./ParentContextBanner";
import type { DocumentRelationship } from "@/api/documents";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: Record<string, unknown>) => (
    <a href={(rest.to as string) ?? ""} {...rest}>
      {children as React.ReactNode}
    </a>
  ),
}));

describe("ParentContextBanner", () => {
  it("renders nothing without relationships", () => {
    render(<ParentContextBanner relationships={null} />);
    expect(screen.queryByText("Attachment of:")).not.toBeInTheDocument();
  });

  it("renders nothing when there is no parent relationship", () => {
    const rels: DocumentRelationship[] = [
      { direction: "child", relationship_type: "attachment", other_document_id: "c1", title: "child", path_in_parent: null },
    ];
    render(<ParentContextBanner relationships={rels} />);
    expect(screen.queryByText("Attachment of:")).not.toBeInTheDocument();
  });

  it("links to the parent document when present", () => {
    const rels: DocumentRelationship[] = [
      { direction: "parent", relationship_type: "attachment", other_document_id: "p1", title: "Quarterly email", path_in_parent: "report.pdf" },
    ];
    render(<ParentContextBanner relationships={rels} />);
    expect(screen.getByText("Attachment of:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quarterly email" })).toBeInTheDocument();
  });
});
