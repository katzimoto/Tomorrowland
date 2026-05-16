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
  can_edit: boolean;
  can_delete: boolean;
}

export interface CommentRaw {
  id: string;
  doc_id?: string;
  author_id: string;
  author_display_name?: string | null;
  author_name?: string;
  author?: CommentAuthor;
  body: string;
  created_at: string;
  edited_at?: string | null;
  updated_at?: string | null;
  can_edit?: boolean;
  can_delete?: boolean;
}

export interface CommentListEnvelope {
  doc_id: string;
  comments: CommentRaw[];
  total: number;
  skip: number;
  limit: number;
}

export interface CommentListParams {
  limit?: number;
  skip?: number;
  offset?: number;
  sort?: "newest" | "oldest" | "created_at" | "-created_at";
}

function backendSort(sort: CommentListParams["sort"]): "newest" | "oldest" | undefined {
  if (sort === "created_at") return "oldest";
  if (sort === "-created_at") return "newest";
  return sort;
}

function toQuery(params: CommentListParams = {}): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const skip = params.skip ?? params.offset;
  if (skip !== undefined) search.set("skip", String(skip));
  const sort = backendSort(params.sort);
  if (sort) search.set("sort", sort);
  const query = search.toString();
  return query ? `?${query}` : "";
}

function mapComment(raw: CommentRaw, docId: string): Comment {
  return {
    id: raw.id,
    doc_id: raw.doc_id ?? docId,
    author_id: raw.author_id,
    author_name: raw.author_display_name ?? raw.author_name,
    author: raw.author,
    body: raw.body,
    created_at: raw.created_at,
    updated_at: raw.edited_at ?? raw.updated_at ?? null,
    can_edit: raw.can_edit ?? false,
    can_delete: raw.can_delete ?? false,
  };
}

export async function listComments(docId: string, params?: CommentListParams): Promise<Comment[]> {
  const envelope = await api.get<CommentListEnvelope>(`/documents/${docId}/comments${toQuery(params)}`);
  return envelope.comments.map((comment) => mapComment(comment, envelope.doc_id));
}

export async function createComment(docId: string, body: string): Promise<Comment> {
  const comment = await api.post<CommentRaw>(`/documents/${docId}/comments`, { body });
  return mapComment(comment, docId);
}

export async function updateComment(docId: string, commentId: string, body: string): Promise<Comment> {
  const comment = await api.patch<CommentRaw>(`/documents/${docId}/comments/${commentId}`, { body });
  return mapComment(comment, docId);
}

export function deleteComment(docId: string, commentId: string): Promise<void> {
  return api.delete<void>(`/documents/${docId}/comments/${commentId}`);
}
