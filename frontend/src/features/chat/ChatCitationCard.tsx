import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { BookmarkPlus } from "lucide-react";
import type { DocumentChatCitation, RetrievalTrace } from "@/api/chat";
import { SaveToEvidencePackDialog } from "@/features/evidence/SaveToEvidencePackDialog";
import { draftFromCitation } from "@/features/evidence/draftFromCitation";
import { useT } from "@/i18n/index";
import styles from "./ChatCitationCard.module.css";

interface ChatCitationCardProps {
  citation: DocumentChatCitation;
  index: number;
  trace?: RetrievalTrace | null;
  onOpenCitation?: (citation: DocumentChatCitation, trace?: RetrievalTrace | null) => void;
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

export function ChatCitationCard({ citation, index, trace, onOpenCitation }: ChatCitationCardProps) {
  const t = useT();
  const [saveOpen, setSaveOpen] = useState(false);
  const title =
    citation.document_title ?? citation.doc_title ?? t.chat.untitledDocument;
  const excerpt = citation.text_excerpt ?? citation.chunk_text ?? "";
  const location = locationLine(citation);
  const isTranslated = citation.translated_from != null;

  function handleClick() {
    onOpenCitation?.(citation, trace);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpenCitation?.(citation, trace);
    }
  }

  return (
    <li
      className={styles.card}
      role={onOpenCitation ? "button" : undefined}
      tabIndex={onOpenCitation ? 0 : undefined}
      onClick={onOpenCitation ? handleClick : undefined}
      onKeyDown={onOpenCitation ? handleKeyDown : undefined}
      aria-label={onOpenCitation ? `${title}${location ? ` — ${location}` : ""}` : undefined}
    >
      <span className={styles.index}>[{index + 1}]</span>
      <div className={styles.body}>
        <span className={styles.title}>{title}</span>
        {location && <span className={styles.location}>{location}</span>}
        {isTranslated && citation.translated_from && (
          <span className={styles.translated}>
            {t.chat.translatedFrom(citation.translated_from)}
          </span>
        )}
        {excerpt && <p className={styles.excerpt}>{excerpt}</p>}
        <div className={styles.actions}>
          <Link
            to="/doc/$docId"
            params={{ docId: citation.document_id }}
            search={{
              page: citation.page_number ?? undefined,
              chunk: citation.chunk_index ?? undefined,
            }}
            className={styles.openLink}
            target="_blank"
            onClick={(e) => e.stopPropagation()}
          >
            {t.chat.openDocument}
          </Link>
          {excerpt && (
            <button
              type="button"
              className={styles.saveBtn}
              onClick={(e) => {
                e.stopPropagation();
                setSaveOpen(true);
              }}
            >
              <BookmarkPlus size={13} />
              {t.chat.saveToEvidencePack}
            </button>
          )}
        </div>
      </div>
      <SaveToEvidencePackDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        draft={draftFromCitation(citation, t.chat.untitledDocument)}
        createdFrom="chat"
      />
    </li>
  );
}
