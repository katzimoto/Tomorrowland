import type { DocumentChatCitation } from "@/api/chat";
import { useT } from "@/i18n/index";
import styles from "./ChatCitationCard.module.css";

interface ChatCitationCardProps {
  citation: DocumentChatCitation;
  index: number;
}

export function ChatCitationCard({ citation, index }: ChatCitationCardProps) {
  const t = useT();
  const title =
    citation.document_title ?? citation.doc_title ?? t.chat.untitledDocument;
  const excerpt = citation.text_excerpt ?? citation.chunk_text ?? "";

  return (
    <li className={styles.card}>
      <span className={styles.index}>[{index + 1}]</span>
      <div className={styles.body}>
        <span className={styles.title}>{title}</span>
        {excerpt && <p className={styles.excerpt}>{excerpt}</p>}
      </div>
    </li>
  );
}
