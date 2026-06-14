import { describe, it, expect } from "vitest";
import { buildJson, buildMarkdown, packFileStem } from "./exportEvidence";
import type { EvidencePackDetail, EvidencePackItem } from "@/api/evidencePacks";

function makeItem(overrides: Partial<EvidencePackItem> = {}): EvidencePackItem {
  return {
    id: "item-1",
    evidence_pack_id: "pack-1",
    document_id: "doc-1",
    item_type: "citation",
    text_excerpt: "The contract terminates on December 31.",
    chunk_id: "chunk-7",
    citation_id: "cit-1",
    page_number: 3,
    section_heading: "Termination",
    translated_text: "החוזה מסתיים ב-31 בדצמבר.",
    claim: "The agreement has a fixed end date.",
    created_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

function makePack(items: EvidencePackItem[]): EvidencePackDetail {
  return {
    id: "pack-1",
    owner_user_id: "user-1",
    title: "Q3 Findings",
    description: "Key passages for the Q3 review.",
    source_scope: null,
    created_from: "chat",
    metadata: {},
    created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    items,
  };
}

describe("buildMarkdown", () => {
  it("includes title, description, and item count", () => {
    const md = buildMarkdown(makePack([makeItem()]));
    expect(md).toContain("# Q3 Findings");
    expect(md).toContain("Key passages for the Q3 review.");
    expect(md).toContain("_1 item(s)_");
  });

  it("preserves citation and source metadata", () => {
    const md = buildMarkdown(makePack([makeItem()]));
    expect(md).toContain("Document: `doc-1`");
    expect(md).toContain("Citation: `cit-1`");
    expect(md).toContain("p. 3 · Termination · chunk chunk-7");
    expect(md).toContain("> The contract terminates on December 31.");
    expect(md).toContain("> _(translated)_ החוזה מסתיים ב-31 בדצמבר.");
    expect(md).toContain("**Claim:** The agreement has a fixed end date.");
  });

  it("omits optional lines when fields are null", () => {
    const md = buildMarkdown(
      makePack([
        makeItem({
          citation_id: null,
          chunk_id: null,
          page_number: null,
          section_heading: null,
          translated_text: null,
          claim: null,
        }),
      ]),
    );
    expect(md).not.toContain("Citation:");
    expect(md).not.toContain("translated");
    expect(md).not.toContain("Claim:");
    expect(md).toContain("Document: `doc-1`");
  });
});

describe("buildJson", () => {
  it("round-trips the full pack including every item field", () => {
    const pack = makePack([makeItem()]);
    const parsed = JSON.parse(buildJson(pack)) as EvidencePackDetail;
    expect(parsed).toEqual(pack);
    expect(parsed.items[0].citation_id).toBe("cit-1");
    expect(parsed.items[0].translated_text).toBe("החוזה מסתיים ב-31 בדצמבר.");
  });
});

describe("packFileStem", () => {
  it("slugifies the title", () => {
    expect(packFileStem(makePack([]))).toBe("q3-findings");
  });

  it("falls back to the pack id when the title has no usable characters", () => {
    const pack = { ...makePack([]), title: "—" };
    expect(packFileStem(pack)).toBe("evidence-pack-pack-1");
  });
});
