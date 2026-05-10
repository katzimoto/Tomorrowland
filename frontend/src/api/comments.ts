import { api } from "./client";

export interface CommentAuthor {
  id: string;
  display_name: string;
}

export interface Comment {
  id: string;
  doc_id: string;
  author_id: string;
  author_name?: string;
  author?: CommentAuthor;
  body: string;
  created_at: string;
  updated_at?: string | null;
}

export interface CommentListParams {
  limit?: number;
  offset?: number;
  sort?: "created_at" | "-created_at";
}

function toQuery(params: CommentListParams = {}): string {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  if (params.sort) search.set("sort", params.sort);
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function listComments(docId: string, params?: CommentListParams): Promise<Comment[]> {
  return api.get<Comment[]>(`/documents/${docId}/comments${toQuery(params)}`);
}

export function createComment(docId: string, body: string): Promise<Comment> {
  return api.post<Comment>(`/documents/${docId}/comments`, { body });
}

export function updateComment(docId: string, commentId: string, body: string): Promise<Comment> {
  return api.patch<Comment>(`/documents/${docId}/comments/${commentId}`, { body });
}

export function deleteComment(docId: string, commentId: string): Promise<void> {
  return api.delete<void>(`/documents/${docId}/comments/${commentId}`);
}
