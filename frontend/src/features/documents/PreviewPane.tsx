import type { DocumentPreview } from "@/api/documents";
import { TextPreview } from "./renderers/TextPreview";
import { MarkdownPreview } from "./renderers/MarkdownPreview";
import { HtmlPreview } from "./renderers/HtmlPreview";
import { TablePreview } from "./renderers/TablePreview";
import { ArchivePreview } from "./renderers/ArchivePreview";
import { EmailManifestPreview } from "./renderers/EmailManifestPreview";
import { OfficeManifestPreview } from "./renderers/OfficeManifestPreview";
import { SlidesPreview } from "./renderers/SlidesPreview";
import { ImageViewer } from "./renderers/ImageViewer";
import { PdfViewer } from "./renderers/PdfViewer";
import { CodeViewer } from "./renderers/CodeViewer";
import { MediaPreview } from "./renderers/MediaPreview";
import { GenericPreview } from "./renderers/GenericPreview";
import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./PreviewPane.module.css";

const MARKDOWN_MIMES = new Set([
  "text/markdown",
  "text/x-markdown",
  "application/markdown",
]);

const MARKDOWN_EXTS = [".md", ".markdown", ".mdown"];

// Extensions that CodeViewer can syntax-highlight (it handles its own EXT_TO_LANGUAGE).
// Used as a fallback when the MIME type is generic (e.g. application/octet-stream).
const CODE_EXTENSIONS = new Set([
  ".json", ".xml", ".yaml", ".yml",
  ".py", ".js", ".jsx", ".ts", ".tsx",
  ".sh", ".bash", ".zsh", ".fish", ".bat", ".ps1",
  ".sql",
  ".rb", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
  ".cs", ".php", ".swift", ".kt", ".scala", ".lua", ".pl", ".r",
  ".toml", ".ini", ".cfg", ".conf", ".env",
  ".tf", ".hcl", ".proto", ".graphql",
]);

// Extensions that render well as plain text
const TEXT_EXTENSIONS = new Set([
  ".txt", ".log", ".nfo", ".readme",
  ".rst", ".adoc", ".asciidoc",
]);

// Extensions that render as Markdown (beyond text/plain handled above)
const MD_EXTENSIONS = new Set([".md", ".markdown", ".mdown", ".mdx"]);

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
  initialPage?: number;
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
  initialPage,
}: PreviewPaneProps) {
  const mime = preview.mime_type;
  const text = preview.snippet;
  const dl = downloadUrl(preview.document_id);

  // In extracted/translation mode, all non-image types render as text.
  // "original" mode is handled per-renderer below (e.g. HTML → raw text, PDF → PDF viewer).
  if (
    !mime.startsWith("image/") &&
    (activeMode === "extracted" ||
      activeMode === "translation")
  ) {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          translationVersionId={activeMode === "translation" ? selectedVersionId : undefined}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime === "text/html") {
    // "original" mode shows the extracted source text rather than the rendered HTML.
    if (activeMode === "original") {
      return (
        <div className={styles.pane}>
          <TextPreview
            docId={preview.document_id}
            showOriginal
            searchQuery={searchQuery}
            activeSearchIndex={activeSearchIndex}
            onMatchCountChange={onMatchCountChange}
          />
        </div>
      );
    }
    return (
      <div className={styles.pane}>
        <HtmlPreview
          html={text ?? ""}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  const isMarkdown =
    MARKDOWN_MIMES.has(mime) ||
    (mime === "text/plain" &&
      preview.title != null &&
      MARKDOWN_EXTS.some((ext) => preview.title!.endsWith(ext)));

  if (isMarkdown) {
    return (
      <div className={styles.pane}>
        <MarkdownPreview
          docId={preview.document_id}
          fallbackText={text ?? ""}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime === "text/plain") {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (mime === "text/csv") {
    return (
      <div className={styles.pane}>
        <TablePreview
          docId={preview.document_id}
          delimiter=","
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
          showOriginal={activeMode !== "translation"}
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
          docId={preview.document_id}
          delimiter="\t"
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
    // Extracted/translation modes are handled by the text block above; here
    // (default/original mode) the manifest-driven high-fidelity viewer renders,
    // with its own fallback to the legacy EmailPreview when the render is
    // unavailable, disabled, or failed.
    return (
      <div className={styles.pane}>
        <EmailManifestPreview
          docId={preview.document_id}
          fallbackText={text ?? ""}
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
    const slidesFallback = (
      <SlidesPreview
        text={text}
        searchQuery={searchQuery}
        activeSearchIndex={activeSearchIndex}
        onMatchCountChange={onMatchCountChange}
      />
    );
    return (
      <div className={styles.pane}>
        <OfficeManifestPreview
          docId={preview.document_id}
          fallback={slidesFallback}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
          initialPage={initialPage}
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
          initialPage={initialPage}
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
    const wordFallback = (
      <TextPreview
        docId={preview.document_id}
        showOriginal={activeMode !== "translation"}
        searchQuery={searchQuery}
        activeSearchIndex={activeSearchIndex}
        onMatchCountChange={onMatchCountChange}
      />
    );
    return (
      <div className={styles.pane}>
        <OfficeManifestPreview
          docId={preview.document_id}
          fallback={wordFallback}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
          initialPage={initialPage}
        />
      </div>
    );
  }

  // Extension-based routing: covers files that arrive with a generic or wrong
  // MIME type (application/octet-stream is the most common case). Derive the
  // renderer from the file extension so the user still gets a real preview.
  const titleExt = (() => {
    const t = preview.title ?? "";
    const dot = t.lastIndexOf(".");
    return dot !== -1 ? t.slice(dot).toLowerCase() : "";
  })();

  if (MD_EXTENSIONS.has(titleExt)) {
    return (
      <div className={styles.pane}>
        <MarkdownPreview
          docId={preview.document_id}
          fallbackText={text ?? ""}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (TEXT_EXTENSIONS.has(titleExt)) {
    return (
      <div className={styles.pane}>
        <TextPreview
          docId={preview.document_id}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  if (CODE_EXTENSIONS.has(titleExt)) {
    return (
      <div className={styles.pane}>
        <CodeViewer
          docId={preview.document_id}
          mimeType={mime}
          title={preview.title ?? undefined}
          showOriginal={activeMode !== "translation"}
          searchQuery={searchQuery}
          activeSearchIndex={activeSearchIndex}
          onMatchCountChange={onMatchCountChange}
        />
      </div>
    );
  }

  // Final fallback: show whatever the backend extracted, with a banner
  // identifying the original MIME type and a download link. TextPreview
  // gracefully shows "No text content available." if extraction produced nothing.
  return (
    <div className={styles.pane}>
      <GenericPreview
        docId={preview.document_id}
        mimeType={mime}
        downloadUrl={dl}
        showOriginal={activeMode !== "translation"}
        searchQuery={searchQuery}
        activeSearchIndex={activeSearchIndex}
        onMatchCountChange={onMatchCountChange}
      />
    </div>
  );
}
