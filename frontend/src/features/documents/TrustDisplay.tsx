import { Badge } from "@/components/primitives/Badge";
import type { DocumentPreview } from "@/api/documents";
import { formatDate } from "@/lib/datetime";
import styles from "./TrustDisplay.module.css";

interface TrustDisplayProps {
  preview: DocumentPreview;
}

export function TrustDisplay({ preview }: TrustDisplayProps) {
  const variant =
    preview.translation_quality === "high" ? "success" :
    preview.translation_quality === "fast" ? "warning" : "neutral";

  const label =
    preview.translation_quality === "high" ? "High quality translation" :
    preview.translation_quality === "fast" ? "Fast translation" : "Not translated";

  const indexedDate = preview.metadata["indexed_at"]
    ? formatDate(String(preview.metadata["indexed_at"]))
    : null;

  return (
    <div className={styles.trust}>
      <Badge variant={variant}>{label}</Badge>
      {preview.high_quality_pending && (
        <Badge variant="neutral">High-quality translation in progress</Badge>
      )}
      {indexedDate && (
        <span className={styles.meta}>Indexed {indexedDate}</span>
      )}
      {preview.view_count > 0 && (
        <span className={styles.meta}>{preview.view_count} {preview.view_count === 1 ? "view" : "views"}</span>
      )}
    </div>
  );
}
