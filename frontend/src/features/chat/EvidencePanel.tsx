import { useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { getPreview } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { DocumentChatCitation } from "@/api/chat";
import { useT } from "@/i18n/index";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { PreviewWithHighlight } from "./PreviewWithHighlight";
import styles from "./EvidencePanel.module.css";

interface EvidencePanelProps {
  citation: DocumentChatCitation;
  onClose: () => void;
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

export function EvidencePanel({ citation, onClose }: EvidencePanelProps) {
  const t = useT();
  const title = citation.document_title ?? citation.doc_title ?? t.chat.untitledDocument;
  const excerpt = citation.text_excerpt ?? citation.chunk_text ?? "";
  const location = locationLine(citation);

  const { data: preview, isLoading, isError, error } = useQuery({
    queryKey: ["evidence-preview", citation.document_id],
    queryFn: () => getPreview(citation.document_id),
    staleTime: 2 * 60_000,
  });

  const apiStatus = error instanceof ApiError ? error.status : null;

  if (isLoading) {
    return (
      <aside className={styles.panel}>
        <header className={styles.header}>
          <span className={styles.headerTitle}>{t.chat.evidenceLoading}</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t.chat.evidenceClose}>
            <X size={18} />
          </button>
        </header>
        <div className={styles.loadingArea}>
          <SkeletonRow count={4} />
        </div>
      </aside>
    );
  }

  if (isError) {
    const errorTitle = apiStatus === 403
      ? t.chat.evidenceForbidden
      : apiStatus === 404
        ? t.chat.evidenceNotFound
        : t.chat.evidenceNoPreview;

    return (
      <aside className={styles.panel}>
        <header className={styles.header}>
          <span className={styles.headerTitle}>{title}</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t.chat.evidenceClose}>
            <X size={18} />
          </button>
        </header>
        <div className={styles.errorState}>
          <p className={styles.errorText}>{errorTitle}</p>
        </div>
      </aside>
    );
  }

  if (!preview) return null;

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.headerInfo}>
          <span className={styles.headerTitle}>{title}</span>
          {location && <span className={styles.location}>{location}</span>}
        </div>
        <div className={styles.headerActions}>
          <Link
            to="/doc/$docId"
            params={{ docId: citation.document_id }}
            search={{
              page: citation.page_number ?? undefined,
              chunk: citation.chunk_index ?? undefined,
            }}
            className={styles.fullPageLink}
            target="_blank"
            aria-label={t.chat.evidenceOpenFullPage}
          >
            <ExternalLink size={16} />
          </Link>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t.chat.evidenceClose}>
            <X size={18} />
          </button>
        </div>
      </header>
      {excerpt && (
        <div className={styles.excerpt}>
          <p className={styles.excerptText}>{excerpt}</p>
        </div>
      )}
      {!excerpt && !location && (
        <div className={styles.noLocation}>
          <p className={styles.noLocationText}>{t.chat.evidenceNoPreview}</p>
        </div>
      )}
      <div className={styles.previewArea}>
        <PreviewWithHighlight preview={preview} citation={citation} />
      </div>
    </aside>
  );
}
