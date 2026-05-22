import { Link } from "@tanstack/react-router";
import type { DocumentChatCitation } from "@/api/chat";
import { useT } from "@/i18n/index";
import styles from "./ChatCitationCard.module.css";

interface ChatCitationCardProps {
  citation: DocumentChatCitation;
  index: number;
}

function locationLine(citation: DocumentChatCitation): string {
  const parts: string[] = [];
  if (citation.page_number != null) {
    parts.push(`p. ${citation.page_number}`);
  }
  if (citation.section_heading) {
    parts.push(citation.section_heading);
  }
  return parts.join(" · ");
}

export function ChatCitationCard({ citation, index }: ChatCitationCardProps) {
  const t = useT();
  const title =
    citation.document_title ?? citation.doc_title ?? t.chat.untitledDocument;
  const excerpt = citation.text_excerpt ?? citation.chunk_text ?? "";
  const location = locationLine(citation);
  const isTranslated = citation.translated_from != null;

  return (
    <li className={styles.card}>
      <span className={styles.index}>[{index + 1}]</span>
      <div className={styles.body}>
        <span className={styles.title}>{title}</span>
        {location && <span className={styles.location}>{location}</span>}
        {isTranslated && (
          <span className={styles.translated}>
            Translated from {citation.translated_from}
          </span>
        )}
        {excerpt && <p className={styles.excerpt}>{excerpt}</p>}
        <Link
          to="/doc/$docId"
          params={{ docId: citation.document_id }}
          search={{
            page: citation.page_number ?? undefined,
            chunk: citation.chunk_index ?? undefined,
          }}
          className={styles.openLink}
          target="_blank"
        >
          Open
        </Link>
      </div>
    </li>
  );
}
