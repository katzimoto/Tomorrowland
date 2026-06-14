import type { DocumentChatCitation } from "@/api/chat";
import type { EvidenceDraft } from "./SaveToEvidencePackDialog";

/**
 * Build a savable evidence draft from a chat citation, preserving the document,
 * citation id, page/section, and excerpt so the stored item stays anchored.
 */
export function draftFromCitation(
  citation: DocumentChatCitation,
  untitledLabel: string,
): EvidenceDraft {
  return {
    document_id: citation.document_id,
    item_type: "citation",
    text_excerpt: citation.text_excerpt ?? citation.chunk_text ?? "",
    citation_id: citation.citation_id ?? null,
    page_number: citation.page_number ?? null,
    section_heading: citation.section_heading ?? null,
    title: citation.document_title ?? citation.doc_title ?? untitledLabel,
  };
}
