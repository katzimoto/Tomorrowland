import { api } from "./client";

export interface Annotation {
  id: string;
  document_id: string;
  author_id: string;
  author_name?: string;
  body: string;
  position?: Record<string, unknown> | null;
  shared: boolean;
  created_at: string;
  updated_at?: string | null;
  can_modify: boolean;
  reply_count?: number;
}

export interface AnnotationRaw {
  id: string;
  document_id?: string;
  user_id: string;
  user_display_name?: string | null;
  text: string;
  note?: string | null;
  position?: Record<string, unknown> | null;
  is_private: boolean;
  created_at: string;
  updated_at?: string | null;
  can_modify?: boolean;
}

export interface AnnotationListEnvelope {
  document_id: string;
  annotations: AnnotationRaw[];
}

export interface AnnotationWrite {
  body: string;
  position?: Record<string, unknown> | null;
  shared: boolean;
}

interface AnnotationWriteRaw {
  text: string;
  position?: Record<string, unknown> | null;
  is_private: boolean;
}

function mapAnnotation(raw: AnnotationRaw, docId?: string): Annotation {
  return {
    id: raw.id,
    document_id: raw.document_id ?? docId ?? "",
    author_id: raw.user_id,
    author_name: raw.user_display_name ?? undefined,
    body: raw.text,
    position: raw.position ?? null,
    shared: !raw.is_private,
    created_at: raw.created_at,
    updated_at: raw.updated_at ?? null,
    can_modify: raw.can_modify ?? false,
  };
}

function mapAnnotationWrite(payload: AnnotationWrite): AnnotationWriteRaw {
  return {
    text: payload.body,
    position: payload.position ?? null,
    is_private: !payload.shared,
  };
}

export async function listAnnotations(docId: string): Promise<Annotation[]> {
  const envelope = await api.get<AnnotationListEnvelope>(`/documents/${docId}/annotations`);
  return envelope.annotations.map((annotation) => mapAnnotation(annotation, envelope.document_id));
}

export async function createAnnotation(docId: string, payload: AnnotationWrite): Promise<Annotation> {
  const annotation = await api.post<AnnotationRaw>(
    `/documents/${docId}/annotations`,
    mapAnnotationWrite(payload),
  );
  return mapAnnotation(annotation, docId);
}

export async function updateAnnotation(annotationId: string, payload: AnnotationWrite): Promise<Annotation> {
  const annotation = await api.put<AnnotationRaw>(`/annotations/${annotationId}`, mapAnnotationWrite(payload));
  return mapAnnotation(annotation);
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return api.delete<void>(`/annotations/${annotationId}`);
}

// ---------------------------------------------------------------------------
// Annotation replies
// ---------------------------------------------------------------------------

export interface AnnotationReplyRaw {
  id: string;
  user_id: string;
  user_display_name?: string | null;
  body: string;
  created_at: string;
  edited_at?: string | null;
  can_modify?: boolean;
}

export interface AnnotationReplyListEnvelope {
  annotation_id: string;
  replies: AnnotationReplyRaw[];
}

export interface AnnotationReply {
  id: string;
  author_id: string;
  author_name?: string;
  body: string;
  created_at: string;
  edited_at?: string | null;
  can_modify: boolean;
}

function mapReply(raw: AnnotationReplyRaw): AnnotationReply {
  return {
    id: raw.id,
    author_id: raw.user_id,
    author_name: raw.user_display_name ?? undefined,
    body: raw.body,
    created_at: raw.created_at,
    edited_at: raw.edited_at ?? null,
    can_modify: raw.can_modify ?? false,
  };
}

export async function listReplies(annotationId: string): Promise<AnnotationReply[]> {
  const envelope = await api.get<AnnotationReplyListEnvelope>(`/annotations/${annotationId}/replies`);
  return envelope.replies.map(mapReply);
}

export async function createReply(annotationId: string, body: string): Promise<AnnotationReply> {
  const raw = await api.post<AnnotationReplyRaw>(`/annotations/${annotationId}/replies`, { body });
  return mapReply(raw);
}

export async function deleteReply(replyId: string): Promise<void> {
  return api.delete<void>(`/annotation-replies/${replyId}`);
}
