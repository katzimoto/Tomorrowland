import { useMemo } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { useT } from "@/i18n/index";
import type { ChatMessage, DocumentChatCitation, RetrievalTrace } from "@/api/chat";
import { ChatCitationList } from "./ChatCitationList";
import styles from "./MessageBubble.module.css";

interface MessageBubbleProps {
  message: ChatMessage;
  onOpenCitation?: (citation: DocumentChatCitation, trace?: RetrievalTrace | null) => void;
}

function renderMarkdown(content: string): string {
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html, { FORBID_TAGS: ["script", "style"] });
}

export function MessageBubble({ message, onOpenCitation }: MessageBubbleProps) {
  const t = useT();
  const isAssistant = message.role === "assistant";

  const assistantHtml = useMemo(
    () => (isAssistant ? renderMarkdown(message.content) : null),
    [isAssistant, message.content],
  );

  return (
    <div
      className={`${styles.bubble} ${isAssistant ? styles.assistant : styles.user}`}
    >
      {isAssistant && assistantHtml ? (
        <div
          className={styles.content}
          dangerouslySetInnerHTML={{ __html: assistantHtml }}
        />
      ) : (
        <p className={styles.content}>{message.content}</p>
      )}
      {isAssistant && message.citations && message.citations.length > 0 && (
        <ChatCitationList
          citations={message.citations}
          trace={message.retrieval_trace}
          onOpenCitation={onOpenCitation}
        />
      )}
      {isAssistant && (
        <p className={styles.groundingNote}>{t.chat.groundingNote}</p>
      )}
      {import.meta.env.DEV && isAssistant && message.rewritten_query && (
        <details className={styles.debugPanel}>
          <summary className={styles.debugSummary}>Debug</summary>
          <pre className={styles.debugQuery}>{message.rewritten_query}</pre>
        </details>
      )}
    </div>
  );
}
