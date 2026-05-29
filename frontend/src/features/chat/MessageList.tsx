import { useEffect, useRef } from "react";
import type { ChatMessage, DocumentChatCitation } from "@/api/chat";
import { MessageBubble } from "./MessageBubble";
import styles from "./MessageList.module.css";

interface MessageListProps {
  messages: ChatMessage[];
  busy?: boolean;
  onOpenCitation?: (citation: DocumentChatCitation) => void;
}

export function MessageList({ messages, busy, onOpenCitation }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className={styles.list} role="log" aria-live="polite" aria-label="Chat messages" aria-busy={busy}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onOpenCitation={onOpenCitation} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
