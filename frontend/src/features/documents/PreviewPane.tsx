import type { DocumentPreview } from "@/api/documents";
import { TextPreview } from "./renderers/TextPreview";
import { HtmlPreview } from "./renderers/HtmlPreview";
import { TablePreview } from "./renderers/TablePreview";
import { ArchivePreview } from "./renderers/ArchivePreview";
import { EmailPreview } from "./renderers/EmailPreview";
import { SlidesPreview } from "./renderers/SlidesPreview";
import { ImageViewer } from "./renderers/ImageViewer";
import { PdfViewer } from "./renderers/PdfViewer";
import { CodeViewer } from "./renderers/CodeViewer";
import { MediaPreview } from "./renderers/MediaPreview";
import { UnsupportedPreview } from "./renderers/UnsupportedPreview";
import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./PreviewPane.module.css";

const CODE_MIMES = new Set([
  "application/json",
  "text/xml",
  "application/xml",
  "text/yaml",
  "application/yaml",
  "application/x-yaml",
  "text/x-python",
  "text/javascript",
  "application/javascript",
  "text/typescript",
  "text/x-typescript",
  "text/x-sh",
  "application/x-shellscript",
  "text/x-sql",
  "application/x-sql",
]);

interface PreviewPaneProps {
  preview: DocumentPreview;
  activeMode?: ViewMode;
  selectedVersionId?: string;
  imageZoom?: number | null;
  onImageZoomChange?: (zoom: number | null) => void;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

function downloadUrl(docId: string) {
  return `/api/download/${docId}`;
}

export function PreviewPane({
  preview,
  activeMode,
  selectedVersionId,
  imageZoom = null,
  onImageZoomChange,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: PreviewPaneProps) {
  const mime = preview.mime_type;
  const text = preview.snippet;
  const dl = downloadUrl(preview.document_id);

  // In extracted/translation mode, all non-HTML/non-image types render as text.
  if (
    (activeMode === "extracted" || activeMode === "translation") &&
    mime !== "text/html" &&
    !mime.startsWith("image/")
  ) {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          translationVersionId={activeMode === "translation" ? selectedVersionId : undefined}
          showOriginal={activeMode === "extracted"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime === "text/html") {
    return (
      <div className={styles.pane}>
        <HtmlPreview html={text} />
      </div>
    );
  }

  if (mime === "text/plain" || mime === "text/markdown" || mime === "text/csv") {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (CODE_MIMES.has(mime)) {
    return (
      <div className={styles.pane}>
        <CodeViewer
          docId={preview.document_id}
          mimeType={mime}
          title={preview.title ?? undefined}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
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
        <TablePreview
          text={text}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
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
        <ArchivePreview
          text={text}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime === "message/rfc822" || mime === "application/vnd.ms-outlook") {
    return (
      <div className={styles.pane}>
        <EmailPreview
          text={text}
          metadata={preview.metadata}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
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
        <SlidesPreview
          text={text}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime.startsWith("audio/") || mime.startsWith("video/")) {
    return (
      <div className={styles.pane}>
        <MediaPreview
          docId={preview.document_id}
          mimeType={mime}
          title={preview.title ?? null}
          snippet={preview.snippet ?? ""}
        />
      </div>
    );
  }

  if (mime.startsWith("image/")) {
    return (
      <div className={styles.pane}>
        <ImageViewer
          docId={preview.document_id}
          mimeType={mime}
          alt={preview.title ?? ""}
          zoom={imageZoom}
          onZoomChange={onImageZoomChange ?? (() => {})}
        />
      </div>
    );
  }

  if (mime === "application/pdf") {
    return (
      <div className={styles.pane}>
        <PdfViewer
          docId={preview.document_id}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (
    mime ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    mime === "application/msword" ||
    mime === "application/rtf"
  ) {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <UnsupportedPreview mimeType={mime} downloadUrl={dl} />
    </div>
  );
}
