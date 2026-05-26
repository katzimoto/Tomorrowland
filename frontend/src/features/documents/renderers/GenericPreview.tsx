import { Download } from "lucide-react";
import { TextPreview } from "./TextPreview";
import styles from "./renderers.module.css";

interface GenericPreviewProps {
  docId: string;
  mimeType: string;
  downloadUrl: string;
  showOriginal?: boolean;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

/**
 * Fallback renderer for file types with no dedicated viewer.
 * Shows the backend-extracted text (the generic extractor runs on every file)
 * with a banner identifying the original MIME type and a download link.
 */
export function GenericPreview({
  docId,
  mimeType,
  downloadUrl,
  showOriginal,
  searchQuery,
  activeSearchIndex,
  onMatchCountChange,
}: GenericPreviewProps) {
  return (
    <div className={styles.genericWrapper}>
      <div className={styles.genericBanner}>
        <span className={styles.genericBannerLabel}>
          Extracted text ·{" "}
          <code className={styles.genericMime}>{mimeType}</code>
        </span>
        <a href={downloadUrl} download className={styles.genericDownload}>
          <Download size={13} />
          Download original
        </a>
      </div>
      <TextPreview
        docId={docId}
        showOriginal={showOriginal}
        searchQuery={searchQuery}
        activeSearchIndex={activeSearchIndex}
        onMatchCountChange={onMatchCountChange}
      />
    </div>
  );
}
