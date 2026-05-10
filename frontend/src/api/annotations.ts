import { api } from "./client";

export interface Annotation {
  id: string;
  doc_id: string;
  author_id: string;
  author_name?: string;
  body: string;
  position?: Record<string, unknown> | null;
  shared: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface AnnotationWrite {
  body: string;
  position?: Record<string, unknown> | null;
  shared: boolean;
}

export function listAnnotations(docId: string): Promise<Annotation[]> {
  return api.get<Annotation[]>(`/documents/${docId}/annotations`);
}

export function createAnnotation(docId: string, payload: AnnotationWrite): Promise<Annotation> {
  return api.post<Annotation>(`/documents/${docId}/annotations`, payload);
}

export function updateAnnotation(annotationId: string, payload: AnnotationWrite): Promise<Annotation> {
  return api.put<Annotation>(`/annotations/${annotationId}`, payload);
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return api.delete<void>(`/annotations/${annotationId}`);
}
