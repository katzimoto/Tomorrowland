import type { ReactNode } from "react";
import { previewArtifactUrl, usePreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import { PdfViewer } from "./PdfViewer";
import styles from "./renderers.module.css";

interface OfficeManifestPreviewProps {
  docId: string;
  /** Extracted-text renderer shown while pending, or when the visual render
   *  is disabled/failed/unavailable (e.g. Word→TextPreview, PPTX→SlidesPreview). */
  fallback: ReactNode;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
  initialPage?: number;
}

/**
 * Manifest-first dispatch for Office documents: render the LibreOffice-converted
 * PDF through the existing PdfViewer once the render is ready, show a preparing
 * state while it is in flight, and fall back to the extracted-text renderer when
 * the render is unavailable, disabled, or failed (zero regression).
 */
export function OfficeManifestPreview({
  docId,
  fallback,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
  initialPage,
}: OfficeManifestPreviewProps) {
  const t = useT();
  const { data: manifest, isLoading, isError } = usePreviewManifest(docId);

  if (isLoading) {
    return <div className={styles.muted}>{t.preview.loading}</div>;
  }

  if (isError || !manifest || manifest.renderer !== "libreoffice_pdf") {
    return <>{fallback}</>;
  }

  if (manifest.status === "pending" || manifest.status === "running") {
    return (
      <div className={styles.muted} aria-live="polite">
        {t.preview.preparing}
      </div>
    );
  }

  const pdfArtifactId = manifest.office?.pdf_artifact_id;
  if ((manifest.status === "ready" || manifest.status === "partial") && pdfArtifactId) {
    return (
      <PdfViewer
        docId={docId}
        src={previewArtifactUrl(docId, pdfArtifactId)}
        searchQuery={searchQuery}
        activeSearchIndex={activeSearchIndex}
        onMatchCountChange={onMatchCountChange}
        initialPage={initialPage}
      />
    );
  }

  // failed, or ready-but-no-pdf → extracted text.
  return <>{fallback}</>;
}
