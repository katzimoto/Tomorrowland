import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  getChatSession,
  sendChatMessage,
  type ChatMessage,
  type ChatSession,
} from "@/api/chat";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import styles from "./ChatWindow.module.css";

function scopeLabel(scopeType: string, t: ReturnType<typeof useT>): string {
  switch (scopeType) {
    case "all_accessible_documents":
      return t.chat.scopeAll;
    case "single_document":
      return t.chat.scopeSingleDocument;
    case "selected_documents":
      return t.chat.scopeSelectedDocuments;
    case "source":
      return t.chat.scopeSource;
    case "folder":
      return t.chat.scopeFolder;
    case "current_search_results":
      return t.chat.scopeSearchResults;
    default:
      return scopeType;
  }
}

interface ChatWindowProps {
  session: ChatSession;
}

export function ChatWindow({ session }: ChatWindowProps) {
  const t = useT();
  const { show: showToast } = useToast();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const seededForSession = useRef<string | null>(null);

  const { data: sessionData, isLoading, isError } = useQuery({
    queryKey: ["chat-session", session.id],
    queryFn: () => getChatSession(session.id),
    staleTime: 5 * 60_000,
  });

  // Reset input when session changes; seed messages once per session from query result
  useEffect(() => {
    setInput("");
    seededForSession.current = null;
    setMessages([]);
  }, [session.id]);

  useEffect(() => {
    if (
      sessionData &&
      seededForSession.current !== session.id
    ) {
      seededForSession.current = session.id;
      setMessages(sessionData.messages ?? []);
    }
  }, [sessionData, session.id]);

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      sendChatMessage(session.id, { content }),
    onMutate: (content) => {
      const optimistic: ChatMessage = {
        id: `optimistic-${Date.now()}`,
        session_id: session.id,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      setInput("");
      return { optimistic };
    },
    onSuccess: (assistantMsg, _content, context) => {
      setMessages((prev) => {
        const withoutOptimistic = prev.filter(
          (m) => m.id !== context?.optimistic.id,
        );
        const userMsg: ChatMessage = {
          ...context!.optimistic,
          id: `user-${Date.now()}`,
        };
        return [...withoutOptimistic, userMsg, assistantMsg];
      });
    },
    onError: (_err, _content, context) => {
      setMessages((prev) =>
        prev.filter((m) => m.id !== context?.optimistic.id),
      );
      showToast("error", t.chat.sendError);
    },
  });

  function handleSubmit() {
    const trimmed = input.trim();
    if (trimmed) sendMutation.mutate(trimmed);
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
        <span className={styles.scopeBadge}>
          {t.chat.chattingWith}: {scopeLabel(session.scope_type, t)}
        </span>
        <span className={styles.sessionTitle}>{session.title}</span>
      </header>
      <MessageList messages={messages} />
      <ChatInput
        value={input}
        onChange={setInput}
        onSubmit={handleSubmit}
        disabled={sendMutation.isPending}
      />
    </div>
  );
}
