import type { DocumentPreview } from "@/api/documents";
import { TextPreview } from "./renderers/TextPreview";
import { HtmlPreview } from "./renderers/HtmlPreview";
import { TablePreview } from "./renderers/TablePreview";
import { ArchivePreview } from "./renderers/ArchivePreview";
import { EmailPreview } from "./renderers/EmailPreview";
import { SlidesPreview } from "./renderers/SlidesPreview";
import { ImagePreview } from "./renderers/ImagePreview";
import { UnsupportedPreview } from "./renderers/UnsupportedPreview";
import styles from "./PreviewPane.module.css";

interface PreviewPaneProps {
  preview: DocumentPreview;
}

function downloadUrl(docId: string) {
  return `/api/download/${docId}`;
}

export function PreviewPane({ preview }: PreviewPaneProps) {
  const mime = preview.mime_type;
  const text = preview.snippet;
  const dl = downloadUrl(preview.document_id);

  if (mime === "text/html") {
    return (
      <div className={styles.pane}>
        <HtmlPreview html={text} />
      </div>
    );
  }

  if (
    mime === "text/plain" ||
    mime === "text/markdown" ||
    mime === "application/json" ||
    mime === "text/csv"
  ) {
    return (
      <div className={styles.pane}>
        <TextPreview docId={preview.document_id} />
      </div>
    );
  }

  if (
    mime ===
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    mime === "application/vnd.ms-excel" ||
    mime === "text/tab-separated-values"
  ) {
    return (
      <div className={styles.pane}>
        <TablePreview text={text} />
      </div>
    );
  }

  if (
    mime === "application/zip" ||
    mime === "application/x-tar" ||
    mime === "application/x-7z-compressed" ||
    mime === "application/x-rar-compressed"
  ) {
    return (
      <div className={styles.pane}>
        <ArchivePreview text={text} />
      </div>
    );
  }

  if (mime === "message/rfc822" || mime === "application/vnd.ms-outlook") {
    return (
      <div className={styles.pane}>
        <EmailPreview text={text} metadata={preview.metadata} />
      </div>
    );
  }

  if (
    mime ===
      "application/vnd.openxmlformats-officedocument.presentationml.presentation" ||
    mime === "application/vnd.ms-powerpoint"
  ) {
    return (
      <div className={styles.pane}>
        <SlidesPreview text={text} />
      </div>
    );
  }

  if (mime.startsWith("image/")) {
    return (
      <div className={styles.pane}>
        <ImagePreview docId={preview.document_id} />
      </div>
    );
  }

  if (
    mime === "application/pdf" ||
    mime ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    mime === "application/msword" ||
    mime === "application/rtf"
  ) {
    return (
      <div className={styles.pane}>
        <TextPreview docId={preview.document_id} />
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <UnsupportedPreview mimeType={mime} downloadUrl={dl} />
    </div>
  );
}
