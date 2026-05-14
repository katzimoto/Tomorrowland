import { api } from "./client";
import type { RelatedDocument } from "./generated-or-shared-types";

export interface DocAnnotation {
  id: string;
  doc_id: string;
  user_id: string;
  text: string;
  note: string | null;
  position: { mode: "text-range"; start_char: number; end_char: number } | null;
  is_private: boolean;
  created_at: string;
  can_modify: boolean;
}

export interface AnnotationCreate {
  text: string;
  note?: string;
  position?: { mode: "text-range"; start_char: number; end_char: number } | null;
  is_private: boolean;
}

export interface DocumentPreview {
  doc_id: string;
  title: string | null;
  mime_type: string;
  translation_quality: "fast" | "high" | null;
  metadata: Record<string, unknown>;
  snippet: string;
  view_count: number;
}

export interface DocumentSummary {
  summary: string;
  model: string;
  updated_at: string;
}

export interface DocumentEntity {
  label: string;
  type: string;
  count: number;
}

interface BackendDocumentEntity {
  id: string;
  name: string;
  type: string;
  frequency: number;
}

interface DocumentEntitiesEnvelope {
  doc_id?: string;
  entities: Array<DocumentEntity | BackendDocumentEntity>;
}

type DocumentEntitiesResponse = DocumentEntitiesEnvelope | BackendDocumentEntity[];

function normalizeDocumentEntity(entity: DocumentEntity | BackendDocumentEntity): DocumentEntity {
  if ("label" in entity && "count" in entity) {
    return entity;
  }
  return {
    label: entity.name,
    type: entity.type,
    count: entity.frequency,
  };
}

export interface Comment {
  id: string;
  doc_id: string;
  author_id: string;
  author_display_name: string;
  body: string;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  can_edit: boolean;
  can_delete: boolean;
}

export interface CommentListResponse {
  comments: Comment[];
  total: number;
}

export type TranslationVersionStatus = "pending" | "processing" | "running" | "done" | "available" | "failed";

export interface TranslationVersion {
  version_id: string;
  version_number: number;
  label: string;
  quality: string;
  status: TranslationVersionStatus;
  target_language: string;
  requested_at: string;
}

export function getPreview(docId: string, translationVersionId?: string): Promise<DocumentPreview> {
  const qs = translationVersionId ? `?translation_version_id=${translationVersionId}` : "";
  return api.get<DocumentPreview>(`/preview/${docId}${qs}`);
}

export function getTranslationVersions(docId: string): Promise<TranslationVersion[]> {
  return api.get<TranslationVersion[]>(`/documents/${docId}/translation-versions`);
}

export function getSummary(docId: string): Promise<DocumentSummary> {
  return api.get<DocumentSummary>(`/documents/${docId}/summary`);
}

export async function getEntities(docId: string): Promise<{ doc_id: string; entities: DocumentEntity[] }> {
  const response = await api.get<DocumentEntitiesResponse>(`/documents/${docId}/entities`);
  if (Array.isArray(response)) {
    return { doc_id: docId, entities: response.map(normalizeDocumentEntity) };
  }
  return {
    doc_id: response.doc_id ?? docId,
    entities: response.entities.map(normalizeDocumentEntity),
  };
}

export function getTags(docId: string): Promise<{ doc_id: string; tags: string[] }> {
  return api.get(`/documents/${docId}/tags`);
}

export function getRelated(docId: string): Promise<{ doc_id: string; related: RelatedDocument[] }> {
  return api.get(`/documents/${docId}/related`);
}

export function requestTranslation(docId: string): Promise<{ doc_id: string; translation_version_id: string; status: string }> {
  return api.post(`/documents/${docId}/translate`, {});
}

export function getDownloadUrl(docId: string): string {
  return `/api/download/${docId}`;
}

export function listComments(docId: string, skip = 0, limit = 20): Promise<CommentListResponse> {
  return api.get(`/documents/${docId}/comments?skip=${skip}&limit=${limit}`);
}

export function createComment(docId: string, body: string): Promise<Comment> {
  return api.post(`/documents/${docId}/comments`, { body });
}

export function updateComment(docId: string, commentId: string, body: string): Promise<Comment> {
  return api.patch(`/documents/${docId}/comments/${commentId}`, { body });
}

export function deleteComment(docId: string, commentId: string): Promise<void> {
  return api.delete(`/documents/${docId}/comments/${commentId}`);
}

export function listAnnotations(docId: string): Promise<{ annotations: DocAnnotation[] }> {
  return api.get(`/documents/${docId}/annotations`);
}

export function createAnnotation(docId: string, data: AnnotationCreate): Promise<DocAnnotation> {
  return api.post(`/documents/${docId}/annotations`, data);
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return api.delete(`/annotations/${annotationId}`);
}
