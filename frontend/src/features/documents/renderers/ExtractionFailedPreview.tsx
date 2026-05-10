import { AlertCircle } from "lucide-react";
import styles from "./renderers.module.css";

interface ExtractionFailedPreviewProps {
  downloadUrl?: string;
}

export function ExtractionFailedPreview({ downloadUrl }: ExtractionFailedPreviewProps) {
  return (
    <div className={styles.fallback} role="status">
      <AlertCircle size={32} className={styles.fallbackIcon} />
      <p className={styles.fallbackTitle}>Text extraction failed</p>
      <p className={styles.fallbackBody}>
        The content of this file could not be extracted for preview.
      </p>
      {downloadUrl && (
        <a href={downloadUrl} download className={styles.fallbackAction}>
          Download original file
        </a>
      )}
    </div>
  );
}
