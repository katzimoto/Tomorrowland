import type { DocumentChatCitation } from "@/api/chat";
import { useT } from "@/i18n/index";
import { ChatCitationCard } from "./ChatCitationCard";
import styles from "./ChatCitationList.module.css";

interface ChatCitationListProps {
  citations: DocumentChatCitation[];
}

export function ChatCitationList({ citations }: ChatCitationListProps) {
  const t = useT();
  if (!citations.length) return null;

  return (
    <div className={styles.wrapper}>
      <p className={styles.heading}>{t.chat.sourcesHeading}</p>
      <ul className={styles.list}>
        {citations.map((c, idx) => (
          <ChatCitationCard
            key={c.citation_id ?? `${c.document_id}-${c.chunk_index ?? idx}`}
            citation={c}
            index={idx}
          />
        ))}
      </ul>
    </div>
  );
}
