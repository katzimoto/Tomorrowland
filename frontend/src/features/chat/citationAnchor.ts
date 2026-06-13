import type { DocumentChatCitation } from "@/api/chat";
import type { CitationPreviewAnchor, PreviewManifest } from "@/api/preview";

type SheetNavItem = { index: number; label: string; artifact_id: string };

/**
 * Build a `CitationPreviewAnchor` from a citation and, where available, the
 * document's `PreviewManifest`.  All fields are optional; renderers degrade
 * gracefully when metadata is absent.
 *
 * Resolution strategy per format:
 * - **PDF / Office (word, slides)**: `pageNumber` from `citation.page_number`.
 * - **XLSX sheets**: tries to match `citation.section_heading` to a sheet name
 *   from manifest navigation; falls back to `citation.page_number` as a
 *   0-based sheet index; then defaults to the first sheet.
 * - **Email**: `textExcerpt` drives body text search/highlight.
 * - **Text / Markdown / CSV / fallback**: `textExcerpt` drives search.
 */
export function buildCitationAnchor(
  citation: DocumentChatCitation,
  manifest?: PreviewManifest | null,
): CitationPreviewAnchor {
  const textExcerpt = citation.text_excerpt ?? citation.chunk_text ?? null;

  const anchor: CitationPreviewAnchor = {
    documentId: citation.document_id,
    citationId: citation.citation_id ?? null,
    previewKind: manifest?.kind ?? null,
    renderer: manifest?.renderer ?? null,
    pageNumber: citation.page_number ?? null,
    chunkIndex: citation.chunk_index ?? null,
    textExcerpt: textExcerpt || null,
  };

  if (manifest?.kind === "office_sheets" && manifest.navigation.items.length > 0) {
    const items = manifest.navigation.items as SheetNavItem[];
    let resolved: SheetNavItem | undefined;

    // Prefer section_heading as sheet name (most reliable).
    if (citation.section_heading) {
      resolved = items.find((s) => s.label === citation.section_heading);
    }
    // Fall back to page_number as 0-based sheet index.
    if (!resolved && citation.page_number != null) {
      resolved = items.find((s) => s.index === citation.page_number);
    }
    // Default to first sheet.
    resolved ??= items[0];

    anchor.sheetIndex = resolved.index;
    anchor.sheetName = resolved.label;
  }

  return anchor;
}
