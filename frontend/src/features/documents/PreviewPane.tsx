import type { DocumentPreview } from "@/api/documents";
import styles from "./PreviewPane.module.css";

interface PreviewPaneProps {
  preview: DocumentPreview;
}

export function PreviewPane({ preview }: PreviewPaneProps) {
  const mime = preview.mime_type;

  if (mime === "text/html") {
    return (
      <div
        className={styles.htmlContent}
        dangerouslySetInnerHTML={{ __html: preview.snippet }}
      />
    );
  }

  return (
    <pre className={styles.textContent}>{preview.snippet || "No preview available."}</pre>
  );
}
