import type { DocumentPreview } from "@/api/documents";
import type { DocumentChatCitation } from "@/api/chat";
import { PreviewPane } from "@/features/documents/PreviewPane";

interface PreviewWithHighlightProps {
  preview: DocumentPreview;
  citation: DocumentChatCitation;
}

export function PreviewWithHighlight({ preview, citation }: PreviewWithHighlightProps) {
  const searchQuery = citation.text_excerpt ?? citation.chunk_text ?? "";
  const initialPage = citation.page_number ?? undefined;

  return (
    <PreviewPane
      preview={preview}
      searchQuery={searchQuery}
      activeSearchIndex={0}
      initialPage={initialPage}
    />
  );
}
