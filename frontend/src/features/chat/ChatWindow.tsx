import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getChatSession,
  sendChatMessageStream,
  type ChatMessage,
  type ChatSession,
  type ChatScopeType,
  type ChatStreamPhase,
} from "@/api/chat";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
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
}

export function ChatWindow({
  session,
  onRequestNewScope,
  isCreatingScope = false,
}: ChatWindowProps) {
  const t = useT();
  const { show: showToast } = useToast();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamPhase, setStreamPhase] = useState<ChatStreamPhase | null>(null);
  const [isSending, setIsSending] = useState(false);
  const seededForSession = useRef<string | null>(null);

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

  async function handleSubmit(overrideContent?: string) {
    const text = typeof overrideContent === "string" ? overrideContent : input;
    const trimmed = text.trim();
    if (!trimmed || sendingRef.current) return;

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
    let content = "";

    try {
      await sendChatMessageStream(
        session.id,
        { content: trimmed },
        (event) => {
          if (event.type === "phase") {
            setStreamPhase(event.phase ?? null);
          } else if (event.type === "token" && event.token) {
            content += event.token;
            setMessages((prev) => {
              const withoutOptimistic = prev.filter(
                (m) => m.id !== optimisticId && !m.id.startsWith("stream-"),
              );
              const userMsg: ChatMessage = { ...optimistic, id: `user-${optimisticId}` };
              const streaming: ChatMessage = {
                id: streamId,
                session_id: session.id,
                role: "assistant",
                content,
                created_at: new Date().toISOString(),
              };
              return [...withoutOptimistic, userMsg, streaming];
            });
          } else if (event.type === "done") {
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
                content: event.answer ?? content,
                citations: event.citations,
                model: event.model,
                latency_ms: event.latency_ms,
                created_at: new Date().toISOString(),
              };
              return [...withoutOptimistic, userMsg, done];
            });
          }
        },
      );
    } catch {
      setMessages((prev) =>
        prev.filter((m) => m.id !== optimisticId && !m.id.startsWith("stream-")),
      );
      showToast("error", t.chat.sendError);
    } finally {
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
        <EmptyState title={t.chat.loadSessionError} />
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
        <MessageList messages={messages} busy={!!streamPhase} />
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
