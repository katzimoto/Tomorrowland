import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { TrustDisplay } from "./TrustDisplay";
import type { DocumentPreview } from "@/api/documents";

const base: DocumentPreview = {
  document_id: "doc-1",
  title: "Test",
  mime_type: "text/plain",
  translation_quality: null,
  translation_score: 0,
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

  it("shows fast badge plus pending indicator while high quality is queued", () => {
    render(
      <TrustDisplay
        preview={{ ...base, translation_quality: "fast", high_quality_pending: true }}
      />
    );
    // The available fast translation is still labelled correctly...
    expect(screen.getByText("Fast translation")).toBeInTheDocument();
    // ...and the queued upgrade is surfaced separately (not "Not translated").
    expect(screen.getByText("High-quality translation in progress")).toBeInTheDocument();
    expect(screen.queryByText("Not translated")).not.toBeInTheDocument();
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
