import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, Languages } from "lucide-react";
import { getDownloadUrl } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import type { DocumentPreview } from "@/api/documents";
import { useT } from "@/i18n/index";
import { TrustDisplay } from "./TrustDisplay";
import { TranslationVersionSelector } from "./TranslationVersionSelector";
import { RequestTranslationDialog } from "./RequestTranslationDialog";
import styles from "./DocumentToolbar.module.css";

interface DocumentToolbarProps {
  preview: DocumentPreview;
  selectedVersionId: string | undefined;
  showOriginal: boolean;
  onVersionChange: (versionId: string | undefined) => void;
  onShowOriginalChange: (showOriginal: boolean) => void;
}

export function DocumentToolbar({
  preview,
  selectedVersionId,
  showOriginal,
  onVersionChange,
  onShowOriginalChange,
}: DocumentToolbarProps) {
  const t = useT();
  const navigate = useNavigate();
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
          <a
            href={getDownloadUrl(preview.document_id)}
            download
            className={styles.downloadLink}
          >
            <Button variant="secondary" size="sm">
              <Download size={14} />
              {t.document.download}
            </Button>
          </a>
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
