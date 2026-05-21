import { api, ApiError } from "./client";
import type { RelatedDocument } from "./generated-or-shared-types";

export interface DocumentPreview {
  document_id: string;
  title: string | null;
  mime_type: string;
  translation_quality: "fast" | "high" | null;
  translation_score: number;
  metadata: Record<string, unknown>;
  snippet: string;
  view_count: number;
  version_number?: number | null;
  is_latest?: boolean | null;
  latest_document_id?: string | null;
  has_newer_version?: boolean | null;
  source_language?: string | null;
  target_language?: string | null;
  status?: string | null;
  content_sha256?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DocumentVersion {
  document_id: string;
  version_number: number;
  is_latest: boolean;
  title: string | null;
  created_at: string;
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
  document_id?: string;
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

export function listDocumentVersions(docId: string): Promise<DocumentVersion[]> {
  return api.get<DocumentVersion[]>(`/documents/${docId}/versions`);
}

export function getPreview(
  docId: string,
  translationVersionId?: string,
  original?: boolean,
): Promise<DocumentPreview> {
  const params = new URLSearchParams();
  if (translationVersionId) params.set("translation_version_id", translationVersionId);
  if (original) params.set("show_original", "true");
  const qs = params.toString();
  return api.get<DocumentPreview>(`/preview/${docId}${qs ? `?${qs}` : ""}`);
}

export function getTranslationVersions(docId: string): Promise<TranslationVersion[]> {
  return api.get<TranslationVersion[]>(`/documents/${docId}/translation-versions`);
}

export async function getSummary(docId: string): Promise<DocumentSummary | null> {
  try {
    return await api.get<DocumentSummary>(`/documents/${docId}/summary`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getEntities(docId: string): Promise<{ document_id: string; entities: DocumentEntity[] }> {
  const response = await api.get<DocumentEntitiesResponse>(`/documents/${docId}/entities`);
  if (Array.isArray(response)) {
    return { document_id: docId, entities: response.map(normalizeDocumentEntity) };
  }
  return {
    document_id: response.document_id ?? docId,
    entities: response.entities.map(normalizeDocumentEntity),
  };
}

export function getTags(docId: string): Promise<{ document_id: string; tags: string[] }> {
  return api.get(`/documents/${docId}/tags`);
}

export function getRelated(docId: string): Promise<{ document_id: string; related: RelatedDocument[] }> {
  return api.get(`/documents/${docId}/related`);
}

export function requestTranslation(docId: string): Promise<{ document_id: string; translation_version_id: string; status: string }> {
  return api.post(`/documents/${docId}/translate`, {});
}

export function getDownloadUrl(docId: string): string {
  return `/api/download/${docId}`;
}

export interface DocumentText {
  text: string;
  total_length: number;
  offset: number;
  limit: number;
  truncated: boolean;
}

export interface GetDocumentTextOptions {
  translationVersionId?: string;
  showOriginal?: boolean;
  offset?: number;
  limit?: number;
}

export function getDocumentText(
  docId: string,
  options: GetDocumentTextOptions = {},
): Promise<DocumentText> {
  const params = new URLSearchParams();
  if (options.translationVersionId) params.set("translation_version_id", options.translationVersionId);
  if (options.showOriginal) params.set("show_original", "true");
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  const qs = params.toString();
  return api.get<DocumentText>(`/documents/${docId}/text${qs ? `?${qs}` : ""}`);
}


