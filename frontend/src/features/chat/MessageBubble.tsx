import { useT } from "@/i18n/index";
import type { ChatMessage, DocumentChatCitation } from "@/api/chat";
import { ChatCitationList } from "./ChatCitationList";
import styles from "./MessageBubble.module.css";

interface MessageBubbleProps {
  message: ChatMessage;
  onOpenCitation?: (citation: DocumentChatCitation) => void;
}

export function MessageBubble({ message, onOpenCitation }: MessageBubbleProps) {
  const t = useT();
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={`${styles.bubble} ${isAssistant ? styles.assistant : styles.user}`}
    >
      <p className={styles.content}>{message.content}</p>
      {isAssistant && message.citations && message.citations.length > 0 && (
        <ChatCitationList citations={message.citations} onOpenCitation={onOpenCitation} />
      )}
      {isAssistant && (
        <p className={styles.groundingNote}>{t.chat.groundingNote}</p>
      )}
      {isAssistant && message.rewritten_query && (
        <details className={styles.debugPanel}>
          <summary className={styles.debugSummary}>Debug</summary>
          <pre className={styles.debugQuery}>{message.rewritten_query}</pre>
        </details>
      )}
    </div>
  );
}
