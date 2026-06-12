import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getChatSession,
  sendChatMessageStream,
  type ChatMessage,
  type ChatSession,
  type ChatScopeType,
  type ChatStreamPhase,
  type DocumentChatCitation,
  type RetrievalTrace,
} from "@/api/chat";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ScopeBadge } from "./ScopeBadge";
import { ScopeSelector } from "./ScopeSelector";
import { StarterQuestions } from "./StarterQuestions";
import styles from "./ChatWindow.module.css";

interface ChatWindowProps {
  session: ChatSession;
  onRequestNewScope?: (scopeType: ChatScopeType, scopeIds: string[]) => void;
  isCreatingScope?: boolean;
  onOpenCitation?: (citation: DocumentChatCitation, trace?: RetrievalTrace | null) => void;
}

export function ChatWindow({
  session,
  onRequestNewScope,
  isCreatingScope = false,
  onOpenCitation,
}: ChatWindowProps) {
  const t = useT();
  const { show: showToast } = useToast();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamPhase, setStreamPhase] = useState<ChatStreamPhase | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendFailed, setSendFailed] = useState(false);
  const seededForSession = useRef<string | null>(null);

  const qc = useQueryClient();
  const { data: sessionData, isLoading, isError } = useQuery({
    queryKey: ["chat-session", session.id],
    queryFn: () => getChatSession(session.id),
    staleTime: 5 * 60_000,
  });

  // Seed messages once per session from query result
  useEffect(() => {
    if (sessionData) {
      if (seededForSession.current !== session.id) {
        seededForSession.current = session.id;
        setInput("");
        setMessages(sessionData.messages ?? []);
      }
    }
  }, [sessionData, session.id]);

  const sendingRef = useRef(false);
  // Throttle streaming state updates to avoid token-by-token re-renders.
  const streamContentRef = useRef("");
  const streamFlushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamStateRef = useRef<{
    optimistic: ChatMessage;
    streamId: string;
    userMsg: ChatMessage;
  } | null>(null);

  function flushStreamContent() {
    streamFlushTimer.current = null;
    const s = streamStateRef.current;
    if (!s) return;
    setMessages((prev) => {
      const withoutOptimistic = prev.filter(
        (m) => m.id !== s.optimistic.id && !m.id.startsWith("stream-"),
      );
      const streaming: ChatMessage = {
        id: s.streamId,
        session_id: session.id,
        role: "assistant",
        content: streamContentRef.current,
        created_at: new Date().toISOString(),
      };
      return [...withoutOptimistic, s.userMsg, streaming];
    });
  }

  async function handleSubmit(overrideContent?: string) {
    const text = typeof overrideContent === "string" ? overrideContent : input;
    const trimmed = text.trim();
    if (!trimmed || sendingRef.current) return;

    setSendFailed(false);
    sendingRef.current = true;
    setIsSending(true);
    const optimisticId = `optimistic-${Date.now()}`;
    const optimistic: ChatMessage = {
      id: optimisticId,
      session_id: session.id,
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimistic]);
    setInput("");

    const streamId = `stream-${Date.now()}`;
    streamContentRef.current = "";
    streamStateRef.current = {
      optimistic,
      streamId,
      userMsg: { ...optimistic, id: `user-${optimisticId}` },
    };

    try {
      await sendChatMessageStream(
        session.id,
        { content: trimmed },
        (event) => {
          if (event.type === "phase") {
            setStreamPhase(event.phase ?? null);
          } else if (event.type === "token" && event.token) {
            streamContentRef.current += event.token;
            // Throttle state updates to ~50ms intervals to reduce re-renders.
            if (!streamFlushTimer.current) {
              streamFlushTimer.current = setTimeout(flushStreamContent, 50);
            }
          } else if (event.type === "done") {
            if (streamFlushTimer.current) {
              clearTimeout(streamFlushTimer.current);
              streamFlushTimer.current = null;
            }
            setStreamPhase(null);
            setMessages((prev) => {
              const withoutOptimistic = prev.filter(
                (m) => m.id !== optimisticId && m.id !== streamId,
              );
              const userMsg: ChatMessage = { ...optimistic, id: `user-${optimisticId}` };
              const done: ChatMessage = {
                id: event.message_id ?? streamId,
                session_id: session.id,
                role: "assistant",
                content: event.answer ?? streamContentRef.current,
                citations: event.citations,
                model: event.model,
                latency_ms: event.latency_ms,
                created_at: new Date().toISOString(),
              };
              return [...withoutOptimistic, userMsg, done];
            });
            streamStateRef.current = null;
          }
        },
      );
    } catch {
      // Keep the user message so the user can see what they sent and retry.
      // Remove only the streaming placeholder; replace optimistic id with a
      // stable user-prefixed id so the message stays in the list.
      setMessages((prev) =>
        prev
          .filter((m) => !m.id.startsWith("stream-"))
          .map((m) =>
            m.id === optimisticId ? { ...m, id: `user-${optimisticId}` } : m,
          ),
      );
      setInput(trimmed);
      setSendFailed(true);
      showToast("error", t.chat.sendError);
    } finally {
      if (streamFlushTimer.current) {
        clearTimeout(streamFlushTimer.current);
        streamFlushTimer.current = null;
      }
      streamContentRef.current = "";
      streamStateRef.current = null;
      sendingRef.current = false;
      setIsSending(false);
      setStreamPhase(null);
    }
  }

  function handleStarterSelect(question: string) {
    void handleSubmit(question);
  }

  if (isLoading) {
    return (
      <div className={styles.window}>
        <div className={styles.loadingArea}>
          <SkeletonRow count={3} />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={styles.window}>
        <EmptyState
          title={t.chat.loadSessionError}
          action={
            <Button
              variant="secondary"
              onClick={() =>
                void qc.invalidateQueries({ queryKey: ["chat-session", session.id] })
              }
            >
              {t.chat.retry}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.window}>
      <header className={styles.header}>
        {onRequestNewScope ? (
          <ScopeSelector
            session={session}
            onNewScope={onRequestNewScope}
            isCreating={isCreatingScope}
          />
        ) : (
          <ScopeBadge
            scopeType={session.scope_type}
            scopeIds={session.scope_ids}
          />
        )}
        <span className={styles.sessionTitle}>{session.title}</span>
      </header>
      {messages.length === 0 ? (
        <StarterQuestions
          scopeType={session.scope_type}
          onSelect={handleStarterSelect}
          disabled={isSending}
        />
      ) : (
        <MessageList messages={messages} busy={!!streamPhase} onOpenCitation={onOpenCitation} />
      )}
      {sendFailed && (
        <EmptyState
          title={t.chat.sendError}
          action={
            <Button variant="secondary" onClick={() => void handleSubmit()}>
              {t.chat.retry}
            </Button>
          }
        />
      )}
      <ChatInput
        value={input}
        onChange={setInput}
        onSubmit={handleSubmit}
        disabled={isSending}
        phase={streamPhase}
        autoFocus={!isLoading && !isError}
      />
    </div>
  );
}
