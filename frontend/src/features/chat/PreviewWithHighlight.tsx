import { useMemo } from "react";
import type { DocumentPreview } from "@/api/documents";
import type { DocumentChatCitation } from "@/api/chat";
import { usePreviewManifest } from "@/api/preview";
import { PreviewPane } from "@/features/documents/PreviewPane";
import { buildCitationAnchor } from "./citationAnchor";

interface PreviewWithHighlightProps {
  preview: DocumentPreview;
  citation: DocumentChatCitation;
}

export function PreviewWithHighlight({ preview, citation }: PreviewWithHighlightProps) {
  const { data: manifest } = usePreviewManifest(preview.document_id);
  const anchor = useMemo(
    () => buildCitationAnchor(citation, manifest),
    [citation, manifest],
  );

  return (
    <PreviewPane
      preview={preview}
      searchQuery={anchor.textExcerpt ?? ""}
      activeSearchIndex={0}
      citationAnchor={anchor}
    />
  );
}
