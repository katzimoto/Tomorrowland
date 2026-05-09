import type { DocumentPreview } from "@/api/documents";
import styles from "./PreviewPane.module.css";

function sanitizeHtml(raw: string): string {
  const doc = new DOMParser().parseFromString(raw, "text/html");
  doc.querySelectorAll("script, style, iframe, object, embed").forEach((el) => el.remove());
  return doc.body.innerHTML;
}

interface PreviewPaneProps {
  preview: DocumentPreview;
}

export function PreviewPane({ preview }: PreviewPaneProps) {
  const mime = preview.mime_type;

  if (mime === "text/html") {
    return (
      <div
        className={styles.htmlContent}
        dangerouslySetInnerHTML={{ __html: sanitizeHtml(preview.snippet) }}
      />
    );
  }

  return (
    <pre className={styles.textContent}>{preview.snippet || "No preview available."}</pre>
  );
}
