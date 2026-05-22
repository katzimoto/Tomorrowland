import { api } from "./client";

export type ChatScopeType =
  | "all_accessible_documents"
  | "single_document"
  | "selected_documents"
  | "source"
  | "folder"
  | "current_search_results";

export interface DocumentChatCitation {
  citation_id: string;
  document_id: string;
  document_title?: string | null;
  doc_title?: string | null;
  source_id: string | null;
  chunk_index: number | null;
  text_excerpt?: string;
  chunk_text?: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  rewritten_query?: string | null;
  citations?: DocumentChatCitation[];
  model?: string | null;
  latency_ms?: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  scope_type: ChatScopeType;
  scope_ids: string[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  message_count: number;
}

export interface ChatSessionWithMessages extends ChatSession {
  messages: ChatMessage[];
}

export interface ListSessionsResponse {
  sessions: ChatSession[];
  total: number;
}

export function listChatSessions(params?: {
  limit?: number;
  offset?: number;
  archived?: boolean;
}): Promise<ListSessionsResponse> {
  const search = new URLSearchParams();
  if (params?.limit !== undefined) search.set("limit", String(params.limit));
  if (params?.offset !== undefined) search.set("offset", String(params.offset));
  if (params?.archived !== undefined) search.set("archived", String(params.archived));
  const qs = search.toString();
  return api.get<ListSessionsResponse>(`/chat/sessions${qs ? `?${qs}` : ""}`);
}

export function createChatSession(input: {
  scope_type: ChatScopeType;
  scope_ids?: string[];
  title?: string | null;
}): Promise<ChatSession> {
  return api.post<ChatSession>("/chat/sessions", input);
}

export function getChatSession(sessionId: string): Promise<ChatSessionWithMessages> {
  return api.get<ChatSessionWithMessages>(`/chat/sessions/${sessionId}`);
}

export function patchChatSession(
  sessionId: string,
  input: { title?: string },
): Promise<ChatSession> {
  return api.patch<ChatSession>(`/chat/sessions/${sessionId}`, input);
}

export function deleteChatSession(sessionId: string): Promise<{ ok: boolean }> {
  return api.delete<{ ok: boolean }>(`/chat/sessions/${sessionId}`);
}

export function sendChatMessage(
  sessionId: string,
  input: { content: string; top_k?: number },
): Promise<ChatMessage> {
  return api.post<ChatMessage>(`/chat/sessions/${sessionId}/messages`, input);
}
