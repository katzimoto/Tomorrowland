import type { EvidencePackDetail, EvidencePackItem } from "@/api/evidencePacks";

/** References (page / section / chunk) rendered as a single inline line. */
function itemRefs(item: EvidencePackItem): string[] {
  const refs: string[] = [];
  if (item.page_number != null) refs.push(`p. ${item.page_number}`);
  if (item.section_heading) refs.push(item.section_heading);
  if (item.chunk_id) refs.push(`chunk ${item.chunk_id}`);
  return refs;
}

/**
 * Render a pack as offline-friendly Markdown. Includes every stored citation
 * and source field (document id, citation id, page/section/chunk, translated
 * excerpt, claim) so the export is self-contained and review-ready. Items are
 * exactly those the caller can still access — the API filters the rest before
 * the pack reaches the client.
 */
export function buildMarkdown(pack: EvidencePackDetail): string {
  const lines: string[] = [`# ${pack.title}`, ""];
  if (pack.description) lines.push(pack.description, "");
  lines.push(`_${pack.items.length} item(s)_`, "");

  pack.items.forEach((item, index) => {
    lines.push(`## ${index + 1}. ${item.item_type}`);
    const refs = itemRefs(item);
    if (refs.length > 0) lines.push(`*${refs.join(" · ")}*`);
    lines.push(`- Document: \`${item.document_id}\``);
    if (item.citation_id) lines.push(`- Citation: \`${item.citation_id}\``);
    lines.push("", `> ${item.text_excerpt}`, "");
    if (item.translated_text) lines.push(`> _(translated)_ ${item.translated_text}`, "");
    if (item.claim) lines.push(`**Claim:** ${item.claim}`, "");
  });

  return lines.join("\n");
}

/** Render the full pack (metadata + every item field) as pretty JSON. */
export function buildJson(pack: EvidencePackDetail): string {
  return JSON.stringify(pack, null, 2);
}

/** Trigger a browser download of in-memory text content. */
export function downloadTextFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Build a filesystem-safe filename stem from a pack title. */
export function packFileStem(pack: EvidencePackDetail): string {
  const slug = pack.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || `evidence-pack-${pack.id}`;
}
