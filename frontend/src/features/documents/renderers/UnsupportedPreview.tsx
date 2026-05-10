import { FileX } from "lucide-react";
import styles from "./renderers.module.css";

interface UnsupportedPreviewProps {
  mimeType: string;
  downloadUrl?: string;
}

export function UnsupportedPreview({ mimeType, downloadUrl }: UnsupportedPreviewProps) {
  return (
    <div className={styles.fallback} role="status">
      <FileX size={32} className={styles.fallbackIcon} />
      <p className={styles.fallbackTitle}>Preview not available</p>
      <p className={styles.fallbackBody}>
        This file type ({mimeType}) cannot be previewed in the browser.
      </p>
      {downloadUrl && (
        <a href={downloadUrl} download className={styles.fallbackAction}>
          Download file
        </a>
      )}
    </div>
  );
}
