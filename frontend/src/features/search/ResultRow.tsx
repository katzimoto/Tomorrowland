import { FileText, Image, Archive, Mail, File, Info } from "lucide-react";
import { Badge } from "@/components/primitives/Badge";
import type { SearchResult } from "@/api/search";
import styles from "./ResultRow.module.css";

function MimeIcon({ mimeType }: { mimeType: string }) {
  if (mimeType.includes("pdf")) return <FileText size={18} />;
  if (mimeType.startsWith("image/")) return <Image size={18} />;
  if (mimeType.includes("zip") || mimeType.includes("tar") || mimeType.includes("archive"))
    return <Archive size={18} />;
  if (mimeType.includes("mail") || mimeType.includes("message"))
    return <Mail size={18} />;
  return <File size={18} />;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 86_400_000) return "Today";
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

interface ResultRowProps {
  result: SearchResult;
  onClick?: () => void;
}

export function ResultRow({ result, onClick }: ResultRowProps) {
  const visibleTags = result.tags.slice(0, 4);
  const extraTags = result.tags.length - visibleTags.length;

  return (
    <div className={styles.row} onClick={onClick} role="listitem" tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick?.()}>
      <div className={styles.left}>
        <span className={styles.mimeIcon} aria-hidden>
          <MimeIcon mimeType={result.mime_type} />
        </span>
        <Badge variant="source">{result.source_label}</Badge>
      </div>

      <div className={styles.main}>
        <span className={styles.title}>{result.title}</span>
        <span className={styles.snippet}>{result.snippet}</span>
        <div className={styles.meta}>
          {visibleTags.map((tag) => (
            <Badge key={tag} variant="tag">{tag}</Badge>
          ))}
          {extraTags > 0 && (
            <Badge variant="neutral">+{extraTags}</Badge>
          )}
          {result.translation_quality && (
            <Badge variant="translation">
              {result.translation_quality === "fast" ? "Fast translation" : "High quality"}
            </Badge>
          )}
        </div>
      </div>

      <div className={styles.right}>
        <span className={styles.date}>{formatDate(result.updated_at)}</span>
        {result.why && result.why.length > 0 && (
          <button className={styles.whyBtn} aria-label="Why this result?" type="button">
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
  );
}
