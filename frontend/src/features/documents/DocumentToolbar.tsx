import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, Languages } from "lucide-react";
import { getDownloadUrl } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import type { DocumentPreview } from "@/api/documents";
import { TrustDisplay } from "./TrustDisplay";
import { TranslationVersionSelector } from "./TranslationVersionSelector";
import { RequestTranslationDialog } from "./RequestTranslationDialog";
import styles from "./DocumentToolbar.module.css";

interface DocumentToolbarProps {
  preview: DocumentPreview;
  selectedVersionId: string | undefined;
  onVersionChange: (versionId: string | undefined) => void;
}

export function DocumentToolbar({
  preview,
  selectedVersionId,
  onVersionChange,
}: DocumentToolbarProps) {
  const navigate = useNavigate();
  const [translationDialogOpen, setTranslationDialogOpen] = useState(false);

  function handleBack() {
    void navigate({ to: "/search", search: () => ({ q: "", mode: "hybrid" }) });
  }

  return (
    <>
      <header className={styles.toolbar}>
        <button className={styles.backBtn} onClick={handleBack} aria-label="Back to search">
          <ArrowLeft size={18} />
        </button>

        <div className={styles.titleGroup}>
          <h1 className={styles.title}>{preview.title ?? "Untitled document"}</h1>
          <TrustDisplay preview={preview} />
        </div>

        <div className={styles.controls}>
          <TranslationVersionSelector
            docId={preview.doc_id}
            selectedVersionId={selectedVersionId}
            onSelect={onVersionChange}
          />
          {preview.translation_quality !== "high" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setTranslationDialogOpen(true)}
            >
              <Languages size={14} />
              Request translation
            </Button>
          )}
          <a href={getDownloadUrl(preview.doc_id)} download className={styles.downloadLink}>
            <Button variant="secondary" size="sm">
              <Download size={14} />
              Download
            </Button>
          </a>
        </div>
      </header>

      <RequestTranslationDialog
        docId={preview.doc_id}
        open={translationDialogOpen}
        onClose={() => setTranslationDialogOpen(false)}
      />
    </>
  );
}
