import { useT } from "@/i18n/index";
import type { ChatMessage } from "@/api/chat";
import { ChatCitationList } from "./ChatCitationList";
import styles from "./MessageBubble.module.css";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const t = useT();
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={`${styles.bubble} ${isAssistant ? styles.assistant : styles.user}`}
    >
      <p className={styles.content}>{message.content}</p>
      {isAssistant && message.citations && message.citations.length > 0 && (
        <ChatCitationList citations={message.citations} />
      )}
      {isAssistant && (
        <p className={styles.groundingNote}>{t.chat.groundingNote}</p>
      )}
    </div>
  );
}
