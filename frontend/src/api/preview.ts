import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type PreviewStatus = "pending" | "running" | "ready" | "partial" | "failed";

export interface PreviewManifestArtifact {
  id: string;
  role?: string;
  content_type: string;
  size_bytes?: number;
}

export interface PreviewManifestAttachment {
  filename: string;
  content_type: string;
  size_bytes: number | null;
  document_id: string | null;
  preview_available: boolean;
  inline: boolean;
}

export interface PreviewManifestQuotedRange {
  start_line: number;
  end_line: number;
  label: string;
}

export interface PreviewEmailManifest {
  subject: string | null;
  from: string | null;
  to: string[];
  cc: string[];
  bcc: string[];
  date: string | null;
  message_id: string | null;
  in_reply_to: string | null;
  has_html_body: boolean;
  has_text_body: boolean;
  quoted_ranges: PreviewManifestQuotedRange[];
  inline_images: { content_id: string; content_type: string; size_bytes: number }[];
  skipped_inline_images: number;
  blocked_remote_images: number;
  embedded_inline_images: number;
  attachments: PreviewManifestAttachment[];
}

export interface PreviewManifest {
  document_id: string;
  cache_key: string | null;
  kind: "email" | "office_doc" | "office_slides" | "office_sheets" | "pdf" | "image" | "text";
  renderer: string;
  status: PreviewStatus;
  error: { category: string; detail: string | null } | null;
  generated_at: string | null;
  retry_after_ms: number | null;
  navigation: { unit: string; count: number; items: unknown[] };
  artifacts: PreviewManifestArtifact[];
  email: PreviewEmailManifest | null;
  office: { pdf_artifact_id: string | null; page_count: number | null; text_fallback: boolean } | null;
  evidence: { supports_text_search: boolean; anchor_unit: string; regions_available: boolean };
}

/**
 * Format-aware anchor that connects a RAG citation to an exact preview target.
 *
 * Consumers should call `buildCitationAnchor` (see
 * `src/features/chat/citationAnchor.ts`) to build one from a
 * `DocumentChatCitation` and, optionally, the document's `PreviewManifest`.
 * Fields are optional; renderers degrade gracefully when metadata is absent.
 */
export interface CitationPreviewAnchor {
  documentId: string;
  citationId?: string | null;
  previewKind?: "pdf" | "office_doc" | "office_slides" | "office_sheets" | "email" | "image" | "text" | null;
  renderer?: string | null;
  pageNumber?: number | null;
  sheetIndex?: number | null;
  sheetName?: string | null;
  rowIndex?: number | null;
  colIndex?: number | null;
  chunkIndex?: number | null;
  layoutBlockId?: string | null;
  bbox?: { x: number; y: number; width: number; height: number } | null;
  textExcerpt?: string | null;
  highlightStart?: number | null;
  highlightEnd?: number | null;
}

export function getPreviewManifest(docId: string): Promise<PreviewManifest> {
  return api.get<PreviewManifest>(`/preview/${docId}/manifest`);
}

/** URL for a binary preview artifact (e.g. an Office document's converted PDF),
 *  loaded the same way as the original-file download endpoint. */
export function previewArtifactUrl(docId: string, artifactId: string): string {
  return `/api/preview/${docId}/artifact/${artifactId}`;
}

/** Admin-only: discard the cached preview render so the next manifest request
 *  re-renders the document. */
export function rerenderPreview(docId: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`/admin/preview/${docId}/rerender`, {});
}

/** Fetch a preview artifact as raw text (HTML/plain body). Auth header is
 *  attached by the API client — an `<iframe src>` cannot, which is why HTML
 *  artifacts are loaded here and rendered via `srcdoc`. */
export function getPreviewArtifactText(docId: string, artifactId: string): Promise<string> {
  return api.getText(`/preview/${docId}/artifact/${artifactId}`);
}

const ACTIVE_STATUSES: ReadonlySet<PreviewStatus> = new Set(["pending", "running"]);

/** Poll the manifest while a render is in flight; stop once it settles. */
export function usePreviewManifest(docId: string | undefined) {
  return useQuery({
    queryKey: ["preview-manifest", docId],
    queryFn: () => getPreviewManifest(docId!),
    enabled: !!docId,
    staleTime: 30_000,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ACTIVE_STATUSES.has(status) ? (query.state.data?.retry_after_ms ?? 1500) : false;
    },
  });
}
