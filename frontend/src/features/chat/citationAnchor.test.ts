import { describe, it, expect } from "vitest";
import { buildCitationAnchor } from "./citationAnchor";
import type { DocumentChatCitation } from "@/api/chat";
import type { PreviewManifest } from "@/api/preview";

function makeCitation(overrides: Partial<DocumentChatCitation> = {}): DocumentChatCitation {
  return {
    citation_id: "cit-1",
    document_id: "doc-1",
    doc_title: "Test.pdf",
    chunk_text: "relevant text excerpt",
    score: 0.9,
    chunk_index: 2,
    source_id: null,
    ...overrides,
  };
}

function makeManifest(overrides: Partial<PreviewManifest> = {}): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: null,
    kind: "pdf",
    renderer: "pdf",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: { unit: "page", count: 10, items: [] },
    artifacts: [],
    email: null,
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "page", regions_available: false },
    ...overrides,
  };
}

describe("buildCitationAnchor", () => {
  it("sets documentId and citationId from citation", () => {
    const anchor = buildCitationAnchor(makeCitation({ citation_id: "cit-42", document_id: "doc-99" }));
    expect(anchor.documentId).toBe("doc-99");
    expect(anchor.citationId).toBe("cit-42");
  });

  it("sets pageNumber from citation.page_number (PDF/Office anchor)", () => {
    const anchor = buildCitationAnchor(makeCitation({ page_number: 5 }));
    expect(anchor.pageNumber).toBe(5);
  });

  it("sets pageNumber to null when page_number is absent", () => {
    const anchor = buildCitationAnchor(makeCitation({ page_number: undefined }));
    expect(anchor.pageNumber).toBeNull();
  });

  it("sets textExcerpt from text_excerpt when present (email/text anchor)", () => {
    const anchor = buildCitationAnchor(makeCitation({ text_excerpt: "from the excerpt field" }));
    expect(anchor.textExcerpt).toBe("from the excerpt field");
  });

  it("falls back to chunk_text when text_excerpt is absent", () => {
    const anchor = buildCitationAnchor(
      makeCitation({ text_excerpt: undefined, chunk_text: "chunk body text" }),
    );
    expect(anchor.textExcerpt).toBe("chunk body text");
  });

  it("sets textExcerpt to null when both text_excerpt and chunk_text are absent", () => {
    const anchor = buildCitationAnchor(
      makeCitation({ text_excerpt: undefined, chunk_text: undefined }),
    );
    expect(anchor.textExcerpt).toBeNull();
  });

  it("sets chunkIndex from citation.chunk_index", () => {
    const anchor = buildCitationAnchor(makeCitation({ chunk_index: 7 }));
    expect(anchor.chunkIndex).toBe(7);
  });

  it("uses manifest kind and renderer when manifest is provided", () => {
    const anchor = buildCitationAnchor(
      makeCitation(),
      makeManifest({ kind: "office_doc", renderer: "office_pdf" }),
    );
    expect(anchor.previewKind).toBe("office_doc");
    expect(anchor.renderer).toBe("office_pdf");
  });

  it("leaves previewKind null when manifest is absent", () => {
    const anchor = buildCitationAnchor(makeCitation());
    expect(anchor.previewKind).toBeNull();
  });

  describe("XLSX sheet anchor", () => {
    const sheetManifest = makeManifest({
      kind: "office_sheets",
      renderer: "sheet_grid",
      navigation: {
        unit: "sheet",
        count: 3,
        items: [
          { index: 0, label: "Summary", artifact_id: "a1" },
          { index: 1, label: "Details", artifact_id: "a2" },
          { index: 2, label: "Config", artifact_id: "a3" },
        ],
      },
    });

    it("resolves sheetName from section_heading", () => {
      const anchor = buildCitationAnchor(
        makeCitation({ section_heading: "Details" }),
        sheetManifest,
      );
      expect(anchor.sheetIndex).toBe(1);
      expect(anchor.sheetName).toBe("Details");
    });

    it("falls back to page_number as sheet index when section_heading does not match", () => {
      const anchor = buildCitationAnchor(
        makeCitation({ section_heading: "NonExistent", page_number: 2 }),
        sheetManifest,
      );
      expect(anchor.sheetIndex).toBe(2);
      expect(anchor.sheetName).toBe("Config");
    });

    it("defaults to first sheet when no section_heading or page_number match", () => {
      const anchor = buildCitationAnchor(
        makeCitation({ section_heading: null, page_number: null }),
        sheetManifest,
      );
      expect(anchor.sheetIndex).toBe(0);
      expect(anchor.sheetName).toBe("Summary");
    });

    it("does not set sheetIndex/sheetName for non-sheet manifests", () => {
      const anchor = buildCitationAnchor(
        makeCitation({ section_heading: "Summary" }),
        makeManifest({ kind: "pdf" }),
      );
      expect(anchor.sheetIndex).toBeUndefined();
      expect(anchor.sheetName).toBeUndefined();
    });
  });

  describe("missing metadata fallback", () => {
    it("produces a valid anchor with only documentId when all optional fields are absent", () => {
      const anchor = buildCitationAnchor(
        makeCitation({
          page_number: undefined,
          chunk_index: null,
          section_heading: null,
          text_excerpt: undefined,
          chunk_text: undefined,
        }),
      );
      expect(anchor.documentId).toBe("doc-1");
      expect(anchor.pageNumber).toBeNull();
      expect(anchor.chunkIndex).toBeNull();
      expect(anchor.textExcerpt).toBeNull();
      expect(anchor.sheetIndex).toBeUndefined();
    });
  });
});
