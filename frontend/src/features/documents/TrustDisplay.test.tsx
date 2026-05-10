import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { TrustDisplay } from "./TrustDisplay";
import type { DocumentPreview } from "@/api/documents";

const base: DocumentPreview = {
  doc_id: "doc-1",
  title: "Test",
  mime_type: "text/plain",
  translation_quality: null,
  metadata: {},
  snippet: "",
  view_count: 0,
};

describe("TrustDisplay", () => {
  it("shows 'Not translated' for null quality", () => {
    render(<TrustDisplay preview={base} />);
    expect(screen.getByText("Not translated")).toBeInTheDocument();
  });

  it("shows 'High quality translation' badge", () => {
    render(<TrustDisplay preview={{ ...base, translation_quality: "high" }} />);
    expect(screen.getByText("High quality translation")).toBeInTheDocument();
  });

  it("shows 'Fast translation' badge", () => {
    render(<TrustDisplay preview={{ ...base, translation_quality: "fast" }} />);
    expect(screen.getByText("Fast translation")).toBeInTheDocument();
  });

  it("shows view count when > 0", () => {
    render(<TrustDisplay preview={{ ...base, view_count: 5 }} />);
    expect(screen.getByText("5 views")).toBeInTheDocument();
  });

  it("shows singular view when count is 1", () => {
    render(<TrustDisplay preview={{ ...base, view_count: 1 }} />);
    expect(screen.getByText("1 view")).toBeInTheDocument();
  });

  it("does not show view count when 0", () => {
    render(<TrustDisplay preview={{ ...base, view_count: 0 }} />);
    expect(screen.queryByText(/view/)).not.toBeInTheDocument();
  });
});
