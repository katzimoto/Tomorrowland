import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/api/chat";
import { MessageBubble } from "./MessageBubble";
import styles from "./MessageList.module.css";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className={styles.list} role="log" aria-live="polite" aria-label="Chat messages">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
