import { EventSourceParserStream } from "eventsource-parser/stream";
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
  page_number?: number | null;
  section_heading?: string | null;
  language?: string | null;
  translated_from?: string | null;
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

export type ChatStreamPhase = "searching" | "reading_sources" | "generating";

export interface ChatStreamEvent {
  type: "phase" | "token" | "done";
  phase?: ChatStreamPhase;
  token?: string;
  answer?: string;
  citations?: DocumentChatCitation[];
  message_id?: string;
  model?: string;
  latency_ms?: number;
}

export async function sendChatMessageStream(
  sessionId: string,
  input: { content: string; top_k?: number },
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const token = sessionStorage.getItem("tomorrowland_token");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`/api/chat/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch (err) {
      console.warn("Failed to parse error response body", err);
    }
    throw new Error(message);
  }

  if (!res.body) return;

  const stream = res.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream());

  for await (const event of stream) {
    try {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      if (event.event === "phase") {
        onEvent({ type: "phase", phase: data.phase as ChatStreamPhase });
      } else if (event.event === "token") {
        onEvent({ type: "token", token: data.token as string });
      } else if (event.event === "done") {
        onEvent({
          type: "done",
          answer: data.answer as string,
          citations: data.citations as DocumentChatCitation[],
          message_id: data.message_id as string,
          model: data.model as string,
          latency_ms: data.latency_ms as number,
        });
      }
    } catch { /* skip malformed JSON */ }
  }
}
