import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, Languages, Search } from "lucide-react";
import { getDownloadUrl } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import type { DocumentPreview } from "@/api/documents";
import { useT } from "@/i18n/index";
import { useToast } from "@/components/primitives/ToastContext";
import { TrustDisplay } from "./TrustDisplay";
import { TranslationVersionSelector } from "./TranslationVersionSelector";
import { RequestTranslationDialog } from "./RequestTranslationDialog";
import { ViewModeSwitcher } from "./ViewModeSwitcher";
import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./DocumentToolbar.module.css";

const ZOOM_STEPS = [25, 50, 75, 100, 125, 150, 200, 300, 400];

interface DocumentToolbarProps {
  preview: DocumentPreview;
  selectedVersionId: string | undefined;
  showOriginal: boolean;
  availableModes: ViewMode[];
  activeMode: ViewMode;
  showImageControls?: boolean;
  imageZoom?: number | null;
  onVersionChange: (versionId: string | undefined) => void;
  onShowOriginalChange: (showOriginal: boolean) => void;
  onModeChange: (mode: ViewMode) => void;
  onImageZoomChange?: (zoom: number | null) => void;
  searchable?: boolean;
  searchOpen?: boolean;
  onSearchToggle?: () => void;
  searchBtnRef?: React.RefObject<HTMLButtonElement | null>;
}

export function DocumentToolbar({
  preview,
  selectedVersionId,
  showOriginal,
  availableModes,
  activeMode,
  showImageControls = false,
  imageZoom = null,
  onVersionChange,
  onShowOriginalChange,
  onModeChange,
  onImageZoomChange,
  searchable = false,
  searchOpen = false,
  onSearchToggle,
  searchBtnRef,
}: DocumentToolbarProps) {
  const t = useT();
  const navigate = useNavigate();
  const { show: showToast } = useToast();
  const [translationDialogOpen, setTranslationDialogOpen] = useState(false);

  function handleBack() {
    void navigate({ to: "/search", search: () => ({ q: "", mode: "hybrid" }) });
  }

  return (
    <>
      <header className={styles.toolbar}>
        <button
          className={styles.backBtn}
          onClick={handleBack}
          aria-label={t.document.backToSearch}
        >
          <ArrowLeft size={18} />
        </button>

        <div className={styles.titleGroup}>
          <h1 className={styles.title}>
            {preview.title ?? t.document.untitled}
          </h1>
          <TrustDisplay preview={preview} />
        </div>

        <div className={styles.controls}>
          <ViewModeSwitcher
            availableModes={availableModes}
            activeMode={activeMode}
            onModeChange={onModeChange}
          />
          <TranslationVersionSelector
            docId={preview.document_id}
            selectedVersionId={selectedVersionId}
            showOriginal={showOriginal}
            onSelect={onVersionChange}
            onShowOriginalChange={onShowOriginalChange}
          />
          {preview.translation_quality !== "high" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setTranslationDialogOpen(true)}
            >
              <Languages size={14} />
              {t.document.requestTranslation}
            </Button>
          )}
          {showImageControls && onImageZoomChange && (
            <div className={styles.imageZoomControls}>
              <button
                className={styles.zoomBtn}
                aria-label="Zoom out"
                disabled={imageZoom !== null && imageZoom <= ZOOM_STEPS[0]}
                onClick={() => {
                  if (imageZoom === null || imageZoom <= ZOOM_STEPS[0]) {
                    onImageZoomChange(null);
                  } else {
                    const below = ZOOM_STEPS.filter((s) => s < imageZoom);
                    onImageZoomChange(below.length ? below[below.length - 1] : null);
                  }
                }}
              >
                −
              </button>
              <span className={styles.zoomLevel} aria-live="polite">
                {imageZoom === null ? "Fit" : `${imageZoom}%`}
              </span>
              <button
                className={styles.zoomBtn}
                aria-label="Zoom in"
                disabled={imageZoom !== null && imageZoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
                onClick={() => {
                  if (imageZoom === null) {
                    onImageZoomChange(100);
                  } else {
                    const above = ZOOM_STEPS.filter((s) => s > imageZoom);
                    onImageZoomChange(above.length ? above[0] : imageZoom);
                  }
                }}
              >
                +
              </button>
              <button
                className={styles.zoomBtn}
                aria-label="Reset zoom"
                onClick={() => onImageZoomChange(null)}
              >
                ↺
              </button>
            </div>
          )}
          {searchable && onSearchToggle && (
            <button
              ref={searchBtnRef}
              className={`${styles.searchBtn} ${searchOpen ? styles.searchBtnActive : ""}`}
              aria-label="Search within document"
              aria-pressed={searchOpen}
              onClick={onSearchToggle}
            >
              <Search size={14} />
            </button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const token = sessionStorage.getItem("tomorrowland_token");
              const url = getDownloadUrl(preview.document_id, {
                showOriginal: activeMode !== "translation",
                translationVersionId: activeMode === "translation" ? selectedVersionId : undefined,
              });
              fetch(url, { headers: { Authorization: `Bearer ${token || ""}` } })
                .then((r) => {
                  if (!r.ok) throw new Error(`HTTP ${r.status}`);
                  return r.blob();
                })
                .then((blob) => {
                  const a = document.createElement("a");
                  a.href = URL.createObjectURL(blob);
                  a.download = blob.type.includes("text/plain")
                    ? `${preview.title || preview.document_id}.txt`
                    : (preview.title || preview.document_id);
                  a.click();
                  URL.revokeObjectURL(a.href);
                })
                .catch(() => {
                  showToast("error", t.document.downloadError);
                });
            }}
          >
            <Download size={14} />
            {activeMode === "translation"
              ? t.document.downloadTranslation
              : preview.has_file
                ? t.document.download
                : t.document.downloadText}
          </Button>
        </div>
      </header>

      <RequestTranslationDialog
        docId={preview.document_id}
        open={translationDialogOpen}
        onClose={() => setTranslationDialogOpen(false)}
      />
    </>
  );
}
