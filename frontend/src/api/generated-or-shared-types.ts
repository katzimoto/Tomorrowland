// Shared type definitions mirroring backend response contracts.
// See docs/design/user-ui-spec.md for canonical shapes.

export type TranslationQuality = "fast" | "high" | null;

export interface RelatedDocument {
  doc_id: string;
  title: string;
  source_label: string;
  reason: "same_source" | "shared_entities" | "semantic_similarity" | "linked_issue";
  score?: number;
}

export type PreviewAnchorPosition =
  | { mode: "text-range"; start_char: number; end_char: number }
  | { mode: "page-region"; page: number; x: number; y: number; width: number; height: number; unit: "ratio" }
  | { mode: "table-cell"; row: number; column_key: string }
  | { mode: "archive-entry"; path: string }
  | { mode: "email-section"; section: "header" | "body" | "attachment"; attachment_name?: string };

export interface PreviewAnchor {
  anchor_id: string;
  label?: string;
  position: PreviewAnchorPosition;
}

export interface Annotation {
  annotation_id: string;
  doc_id: string;
  author_id: string;
  author_display_name: string;
  body: string;
  visibility: "private" | "source-readers";
  position: PreviewAnchorPosition;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
  can_delete: boolean;
}
