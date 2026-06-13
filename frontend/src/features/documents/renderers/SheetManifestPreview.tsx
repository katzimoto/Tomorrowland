import type { ReactNode } from "react";
import { usePreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import { SheetViewer } from "./SheetViewer";
import styles from "./renderers.module.css";

interface SheetManifestPreviewProps {
  docId: string;
  /** Extracted-text/table renderer shown while pending, or when the sheet-grid
   *  render is disabled, failed, or unavailable. */
  fallback: ReactNode;
  searchQuery?: string;
  onMatchCountChange?: (count: number) => void;
  /** 0-based sheet index from the citation anchor; navigates to the target sheet. */
  initialSheetIndex?: number | null;
  /** Sheet name from the citation anchor; used as a fallback when index is absent. */
  initialSheetName?: string | null;
}

/**
 * Manifest-first dispatch for spreadsheets: render structured sheet grids once
 * the render is ready, show a preparing state while it is in flight, and fall
 * back to the extracted-text table renderer when the render is unavailable,
 * disabled, or failed (zero regression).
 */
export function SheetManifestPreview({
  docId,
  fallback,
  searchQuery = "",
  onMatchCountChange,
  initialSheetIndex = null,
  initialSheetName = null,
}: SheetManifestPreviewProps) {
  const t = useT();
  const { data: manifest, isLoading, isError } = usePreviewManifest(docId);

  if (isLoading) {
    return <div className={styles.muted}>{t.preview.loading}</div>;
  }

  if (isError || !manifest || manifest.renderer !== "sheet_grid") {
    return <>{fallback}</>;
  }

  if (manifest.status === "pending" || manifest.status === "running") {
    return (
      <div className={styles.muted} aria-live="polite">
        {t.preview.preparing}
      </div>
    );
  }

  if (
    (manifest.status === "ready" || manifest.status === "partial") &&
    manifest.navigation.items.length > 0
  ) {
    return (
      <SheetViewer
        manifest={manifest}
        docId={docId}
        searchQuery={searchQuery}
        onMatchCountChange={onMatchCountChange}
        initialSheetIndex={initialSheetIndex}
        initialSheetName={initialSheetName}
      />
    );
  }

  return <>{fallback}</>;
}
