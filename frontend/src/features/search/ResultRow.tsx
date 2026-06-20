import { useState } from "react";
import { FileText, Image, Archive, Mail, File, Info, Eye, BookmarkPlus } from "lucide-react";
import { Badge } from "@/components/primitives/Badge";
import { VersionBadge } from "@/features/documents/VersionBadge";
import { SaveToEvidencePackDialog } from "@/features/evidence/SaveToEvidencePackDialog";
import DOMPurify from "dompurify";
import { useT } from "@/i18n/index";
import type { SearchResult } from "@/api/search";
import styles from "./ResultRow.module.css";

/** Strip highlight markup to a plain-text excerpt for saving. */
function plainText(raw: string): string {
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS: [] }).trim();
}

/**
 * Safely render Meilisearch highlight snippets.
 * DOMPurify strips all non-<mark> tags; the regex pre-strip is kept as
 * defence-in-depth in case Meilisearch injects unexpected markup.
 */
function highlightHtml(raw: string): string {
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS: ["mark"] });
}

function MimeIcon({ mimeType }: { mimeType: string }) {
  if (mimeType.includes("pdf")) return <FileText size={18} />;
  if (mimeType.startsWith("image/")) return <Image size={18} />;
  if (mimeType.includes("zip") || mimeType.includes("tar") || mimeType.includes("archive"))
    return <Archive size={18} />;
  if (mimeType.includes("mail") || mimeType.includes("message"))
    return <Mail size={18} />;
  return <File size={18} />;
}

function formatDate(iso: string, today: string, daysAgo: (n: number) => string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 86_400_000) return today;
  if (diff < 7 * 86_400_000) return daysAgo(Math.floor(diff / 86_400_000));
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

interface ResultRowProps {
  result: SearchResult;
  id?: string;
  selected?: boolean;
  onClick?: () => void;
  onSelect?: () => void;
  onPreview?: (triggerEl: HTMLButtonElement) => void;
  onPrefetch?: () => void;
}

export function ResultRow({ result, id, selected = false, onClick, onSelect, onPreview, onPrefetch }: ResultRowProps) {
  const t = useT();
  const [saveOpen, setSaveOpen] = useState(false);
  const visibleTags = result.tags.slice(0, 4);
  const extraTags = result.tags.length - visibleTags.length;
  const passageExcerpt = plainText(result.snippet ?? "");

  return (
    <div
      id={id}
      className={`${styles.row} ${selected ? styles.rowSelected : ""}`}
      onClick={onClick}
      onFocus={() => { onSelect?.(); onPrefetch?.(); }}
      onMouseEnter={() => { onSelect?.(); onPrefetch?.(); }}
      role="option"
      aria-selected={selected}
      tabIndex={-1}
    >
      <div className={styles.left}>
        <span className={styles.mimeIcon} aria-hidden>
          <MimeIcon mimeType={result.mime_type} />
        </span>
      </div>

      <div className={styles.main}>
        <span className={styles.title} dangerouslySetInnerHTML={{ __html: highlightHtml(result.title ?? "") }} />
        <span className={styles.snippet} dangerouslySetInnerHTML={{ __html: highlightHtml(result.snippet ?? "") }} />
        <div className={styles.meta}>
          <Badge variant="source">{result.source_label}</Badge>
          {visibleTags.map((tag) => (
            <Badge key={tag} variant="tag">{tag}</Badge>
          ))}
          {extraTags > 0 && (
            <Badge variant="neutral">+{extraTags}</Badge>
          )}
          {result.version_number != null && result.is_latest != null && (
            <VersionBadge versionNumber={result.version_number} isLatest={result.is_latest} />
          )}
          {result.translation_quality && (
            <Badge variant="translation">
              {result.translation_quality === "fast" ? t.filters.transFast : t.filters.transHigh}
            </Badge>
          )}
        </div>
      </div>

      <div className={styles.right}>
        <span className={styles.date}>{formatDate(result.updated_at, t.search.today, t.search.daysAgo)}</span>
        <div className={styles.actions}>
          {onPreview && (
            <button
              className={styles.previewBtn}
              aria-label={t.search.preview(result.title ?? "")}
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onSelect?.();
                onPreview?.(event.currentTarget);
              }}
            >
              <Eye size={14} />
              <span>{t.search.previewLabel}</span>
            </button>
          )}
          {passageExcerpt && (
            <button
              className={styles.previewBtn}
              aria-label={t.search.savePassage}
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setSaveOpen(true);
              }}
            >
              <BookmarkPlus size={14} />
              <span>{t.search.savePassage}</span>
            </button>
          )}
          {result.why && result.why.length > 0 && (
            <button
              className={styles.whyBtn}
              aria-label={t.search.whyThisResult}
              type="button"
              onClick={(event) => event.stopPropagation()}
            >
              <Info size={14} />
              <div className={styles.whyTooltip}>
                {result.why.map((w, i) => (
                  <div key={i}>{w.label}</div>
                ))}
              </div>
            </button>
          )}
        </div>
      </div>
      <SaveToEvidencePackDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        draft={{
          document_id: result.document_id,
          item_type: "passage",
          text_excerpt: passageExcerpt,
          title: result.title,
        }}
        createdFrom="search"
      />
    </div>
  );
}
