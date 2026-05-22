import { useState } from "react";
import { Link } from "@tanstack/react-router";
import type { DocumentPreview } from "@/api/documents";
import { UserTagEditor } from "./UserTagEditor";
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

function formatFileSize(bytes: number | string): string {
  const b = typeof bytes === "string" ? parseInt(bytes, 10) : bytes;
  if (isNaN(b) || b <= 0) return String(bytes);
  return b >= 1_048_576
    ? `${(b / 1_048_576).toFixed(1)} MB`
    : b >= 1024
    ? `${(b / 1024).toFixed(1)} KB`
    : `${b} B`;
}

function truncatePath(path: string, max = 60): string {
  if (path.length <= max) return path;
  return "…" + path.slice(-(max - 1));
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

function SectionHeader({
  title,
  open,
  onToggle,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.sectionHeader}
      aria-expanded={open}
      onClick={onToggle}
    >
      <span className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}>
        ▸
      </span>
      {title}
    </button>
  );
}

interface DetailsTabProps {
  preview: DocumentPreview;
  docId?: string;
}

export function DetailsTab({ preview, docId }: DetailsTabProps) {
  const [copied, setCopied] = useState(false);
  const [rawJson, setRawJson] = useState(false);

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    file: true,
    source: false,
    processing: false,
    intelligence: false,
  });

  function toggleSection(id: string) {
    setOpenSections((prev) => ({ ...prev, [id]: !prev[id] }));
  }

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

  const extension = preview.title?.includes(".")
    ? preview.title.split(".").pop() ?? null
    : preview.mime_type.split("/")[1] ?? null;

  const systemTags = preview.tags ?? [];
  const entities = preview.entities_summary ?? [];

  function handleCopyHash(hash: string) {
    void navigator.clipboard.writeText(hash).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const hasFile =
    !!preview.title || !!preview.mime_type || fileSize != null;
  const hasSource = !!source || !!sourcePath;
  const hasProcessing =
    !!preview.status || preview.version_number != null || !!preview.created_at ||
    !!preview.updated_at || !!preview.content_sha256;
  const hasIntelligence =
    systemTags.length > 0 || entities.length > 0;
  const hasRelationships =
    preview.relationships && preview.relationships.length > 0;
  const hasMeta =
    meta && Object.keys(meta).length > 0;

  const metaEntries = Object.entries(meta)
    .filter(([, v]) => v !== null && v !== undefined && v !== "");

  return (
    <div className={styles.container}>
      {/* File section */}
      {hasFile && (
        <section className={styles.section}>
          <SectionHeader
            title="File"
            open={openSections["file"]}
            onToggle={() => toggleSection("file")}
          />
          {openSections["file"] && (
            <dl className={styles.list}>
              {preview.title && <Row label="File name">{preview.title}</Row>}
              <Row label="File type">{mimeLabel(preview.mime_type)}</Row>
              <Row label="MIME type">
                <code className={styles.code}>{preview.mime_type}</code>
              </Row>
              {extension && <Row label="Extension">{extension}</Row>}
              {fileSize != null && (
                <Row label="File size">{formatFileSize(fileSize)}</Row>
              )}
            </dl>
          )}
        </section>
      )}

      {/* Source section */}
      {hasSource && (
        <section className={styles.section}>
          <SectionHeader
            title="Source"
            open={openSections["source"]}
            onToggle={() => toggleSection("source")}
          />
          {openSections["source"] && (
            <dl className={styles.list}>
              {source && <Row label="Source">{source}</Row>}
              {sourcePath && (
                <Row label="Source path">
                  <span
                    title={String(sourcePath)}
                    className={styles.pathCell}
                  >
                    {truncatePath(String(sourcePath))}
                  </span>
                  {" "}
                  <button
                    type="button"
                    className={styles.copyBtn}
                    aria-label="Copy full path"
                    onClick={() => handleCopyHash(String(sourcePath))}
                  >
                    {copied ? "Copied" : "Copy"}
                  </button>
                </Row>
              )}
              {preview.source_language && (
                <Row label="Original language">{preview.source_language}</Row>
              )}
              {preview.target_language && (
                <Row label="Translation language">{preview.target_language}</Row>
              )}
            </dl>
          )}
        </section>
      )}

      {/* Processing section */}
      {hasProcessing && (
        <section className={styles.section}>
          <SectionHeader
            title="Processing"
            open={openSections["processing"]}
            onToggle={() => toggleSection("processing")}
          />
          {openSections["processing"] && (
            <dl className={styles.list}>
              {preview.status && (
                <Row label="Status">
                  <span className={`${styles.badge} ${styles[`status_${preview.status}`]}`}>
                    {preview.status.charAt(0).toUpperCase() + preview.status.slice(1)}
                  </span>
                </Row>
              )}
              {preview.translation_quality && (
                <Row label="Translation quality">
                  <span className={`${styles.badge} ${styles[`quality_${preview.translation_quality}`]}`}>
                    {preview.translation_quality === "high" ? "High" : "Fast"}
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
              {preview.indexed_at && (
                <Row label="Indexed">{formatDateTime(preview.indexed_at)}</Row>
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
          )}
        </section>
      )}

      {/* Intelligence section */}
      {hasIntelligence && (
        <section className={styles.section}>
          <SectionHeader
            title="Intelligence"
            open={openSections["intelligence"]}
            onToggle={() => toggleSection("intelligence")}
          />
          {openSections["intelligence"] && (
            <dl className={styles.list}>
              {systemTags.length > 0 && (
                <Row label="System tags">
                  <div className={styles.tagList}>
                    {systemTags.map((tag) => (
                      <span key={tag} className={styles.tagChip}>{tag}</span>
                    ))}
                  </div>
                </Row>
              )}
              {entities.length > 0 && (
                <Row label="Entities">
                  {entities.map((e, i) => (
                    <div key={i} className={styles.entityRow}>
                      <span className={styles.entityName}>{e.name}</span>
                      <span className={styles.entityType}>({e.type})</span>
                    </div>
                  ))}
                </Row>
              )}
            </dl>
          )}
        </section>
      )}

      {/* Source context (relationships) */}
      {hasRelationships && (
        <section className={styles.section}>
          <SectionHeaderDefault title="Source context" />
          <div className={styles.relList}>
            {preview.relationships!.map((rel, idx) => (
              <div key={`${rel.other_document_id}-${idx}`} className={styles.relRow}>
                <span className={styles.relBadge}>
                  {rel.direction === "parent" ? "Parent" : "Child"}
                </span>
                <Link
                  to="/doc/$docId"
                  params={{ docId: rel.other_document_id }}
                  className={styles.relLink}
                >
                  {rel.title || rel.other_document_id.slice(0, 8)}
                </Link>
                {rel.path_in_parent && (
                  <span className={styles.relPath}>in {rel.path_in_parent}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* My Tags */}
      {docId && (
        <section className={styles.section}>
          <SectionHeaderDefault title="My Tags" />
          <UserTagEditor docId={docId} />
        </section>
      )}

      {/* Metadata */}
      {hasMeta && (
        <section className={styles.section}>
          <SectionHeaderDefault title="Metadata" />
          <div className={styles.metaToggle}>
            <button
              type="button"
              className={`${styles.toggleBtn} ${!rawJson ? styles.toggleBtnActive : ""}`}
              onClick={() => setRawJson(false)}
            >
              Fields
            </button>
            <button
              type="button"
              className={`${styles.toggleBtn} ${rawJson ? styles.toggleBtnActive : ""}`}
              onClick={() => setRawJson(true)}
            >
              Raw JSON
            </button>
          </div>
          {rawJson ? (
            <pre className={styles.jsonBlock}>
              {JSON.stringify(meta, null, 2)}
            </pre>
          ) : (
            <dl className={styles.list}>
              {metaEntries.map(([key, value]) => (
                <Row key={key} label={key}>
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </Row>
              ))}
            </dl>
          )}
        </section>
      )}
    </div>
  );
}

function SectionHeaderDefault({ title }: { title: string }) {
  return (
    <div className={styles.sectionHeaderStatic}>{title}</div>
  );
}
