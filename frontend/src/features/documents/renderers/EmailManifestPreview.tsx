import { usePreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import { EmailViewer } from "./EmailViewer";
import { EmailPreview } from "./EmailPreview";
import styles from "./renderers.module.css";

interface EmailManifestPreviewProps {
  docId: string;
  /** Snippet/metadata fallback for the legacy text renderer. */
  fallbackText: string;
  metadata: Record<string, unknown>;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

/**
 * Manifest-first dispatch for mail documents: render the high-fidelity
 * EmailViewer once the preview render is ready, show a preparing state while
 * it is in flight, and fall back to the legacy extracted-text EmailPreview
 * whenever the manifest is unavailable, disabled, or failed. Falling back
 * keeps mail preview working with zero regression if the renderer is off.
 */
export function EmailManifestPreview({
  docId,
  fallbackText,
  metadata,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: EmailManifestPreviewProps) {
  const t = useT();
  const { data: manifest, isLoading, isError } = usePreviewManifest(docId);

  const fallback = (
    <EmailPreview
      docId={docId}
      text={fallbackText}
      metadata={metadata}
      searchQuery={searchQuery}
      activeSearchIndex={activeSearchIndex}
      onMatchCountChange={onMatchCountChange}
    />
  );

  if (isLoading) {
    return <div className={styles.muted}>{t.preview.loading}</div>;
  }

  if (isError || !manifest || manifest.kind !== "email") {
    return fallback;
  }

  if (manifest.status === "pending" || manifest.status === "running") {
    return (
      <div className={styles.muted} aria-live="polite">
        {t.preview.preparing}
      </div>
    );
  }

  if (manifest.status === "failed") {
    return fallback;
  }

  // ready | partial — render whatever artifacts exist.
  return (
    <EmailViewer
      manifest={manifest}
      docId={docId}
      searchQuery={searchQuery}
      activeSearchIndex={activeSearchIndex}
      onMatchCountChange={onMatchCountChange}
    />
  );
}
