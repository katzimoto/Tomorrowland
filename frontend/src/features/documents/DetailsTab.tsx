import { useState } from "react";
import type { DocumentPreview } from "@/api/documents";
import styles from "./DetailsTab.module.css";

const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF Document",
  "text/plain": "Plain Text",
  "text/html": "HTML Document",
  "text/markdown": "Markdown",
  "application/json": "JSON",
  "text/csv": "CSV Spreadsheet",
  "text/tab-separated-values": "TSV Spreadsheet",
  "image/png": "PNG Image",
  "image/jpeg": "JPEG Image",
  "image/gif": "GIF Image",
  "image/webp": "WebP Image",
  "image/tiff": "TIFF Image",
  "image/svg+xml": "SVG Image",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
  "application/msword": "Word Document",
  "application/rtf": "Rich Text Document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
  "application/vnd.ms-excel": "Excel Spreadsheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint Presentation",
  "application/vnd.ms-powerpoint": "PowerPoint Presentation",
  "message/rfc822": "Email Message",
  "application/vnd.ms-outlook": "Outlook Message",
  "application/zip": "ZIP Archive",
  "application/x-tar": "TAR Archive",
  "application/x-7z-compressed": "7-Zip Archive",
  "application/x-rar-compressed": "RAR Archive",
};

function mimeLabel(mime: string): string {
  return MIME_LABELS[mime] ?? mime.split("/")[1]?.replace(/[^a-z]/gi, " ") ?? mime;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

interface RowProps {
  label: string;
  children: React.ReactNode;
}

function Row({ label, children }: RowProps) {
  return (
    <div className={styles.row}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.value}>{children}</dd>
    </div>
  );
}

interface DetailsTabProps {
  preview: DocumentPreview;
}

export function DetailsTab({ preview }: DetailsTabProps) {
  const [copied, setCopied] = useState(false);
  const meta = preview.metadata as Record<string, unknown>;

  const source =
    (meta.connector_name as string | undefined) ??
    (meta.source as string | undefined) ??
    (meta.source_name as string | undefined);

  const sourcePath =
    (meta.path as string | undefined) ??
    (meta.source_path as string | undefined);

  const fileSize =
    (meta.file_size as number | string | undefined) ??
    (meta.size as number | string | undefined);

  function handleCopyHash(hash: string) {
    void navigator.clipboard.writeText(hash).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <dl className={styles.list}>
      {preview.title && <Row label="File name">{preview.title}</Row>}

      <Row label="File type">{mimeLabel(preview.mime_type)}</Row>

      <Row label="MIME type">
        <code className={styles.code}>{preview.mime_type}</code>
      </Row>

      {fileSize != null && (
        <Row label="File size">
          {typeof fileSize === "number"
            ? fileSize >= 1_048_576
              ? `${(fileSize / 1_048_576).toFixed(1)} MB`
              : fileSize >= 1024
              ? `${(fileSize / 1024).toFixed(1)} KB`
              : `${fileSize} B`
            : String(fileSize)}
        </Row>
      )}

      {source && <Row label="Source">{source}</Row>}

      {sourcePath && <Row label="Source path">{sourcePath}</Row>}

      {preview.source_language && (
        <Row label="Original language">{preview.source_language}</Row>
      )}

      {preview.target_language && (
        <Row label="Translation language">{preview.target_language}</Row>
      )}

      {preview.translation_quality && (
        <Row label="Translation quality">
          <span className={`${styles.badge} ${styles[`quality_${preview.translation_quality}`]}`}>
            {preview.translation_quality === "high" ? "High" : "Fast"}
          </span>
        </Row>
      )}

      {preview.status && (
        <Row label="Processing status">
          <span className={`${styles.badge} ${styles[`status_${preview.status}`]}`}>
            {preview.status.charAt(0).toUpperCase() + preview.status.slice(1)}
          </span>
        </Row>
      )}

      {preview.version_number != null && (
        <Row label="Version">
          {preview.version_number}
          {preview.is_latest === true && (
            <span className={styles.latestBadge}> (latest)</span>
          )}
        </Row>
      )}

      {preview.created_at && (
        <Row label="Imported">{formatDateTime(preview.created_at)}</Row>
      )}

      {preview.updated_at && (
        <Row label="Updated">{formatDateTime(preview.updated_at)}</Row>
      )}

      {preview.content_sha256 && (
        <Row label="Content SHA-256">
          <span className={styles.hashGroup}>
            <code className={styles.code}>
              {preview.content_sha256.slice(0, 12)}…
            </code>
            <button
              className={styles.copyBtn}
              aria-label="Copy full SHA-256 hash"
              onClick={() => handleCopyHash(preview.content_sha256!)}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </span>
        </Row>
      )}
    </dl>
  );
}
