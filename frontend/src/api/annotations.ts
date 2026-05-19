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
