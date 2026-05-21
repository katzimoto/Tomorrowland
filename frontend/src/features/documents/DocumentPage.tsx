import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getDownloadUrl, getPreview, getTranslationVersions } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import { DocumentToolbar } from "./DocumentToolbar";
import { FidelityStatusBar } from "./FidelityStatusBar";
import { PreviewPane } from "./PreviewPane";
import { InsightPane } from "./InsightPane";
import { VersionBanner } from "./VersionBanner";
import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./DocumentPage.module.css";

export function DocumentPage() {
  const t = useT();
  const { docId } = useParams({ from: "/app/doc/$docId" });
  const [selectedVersionId, setSelectedVersionId] = useState<
    string | undefined
  >(undefined);
  const [activeMode, setActiveMode] = useState<ViewMode>("original");
  const initialModeDoneRef = useRef(false);
  const qc = useQueryClient();
  const hadInProgressRef = useRef(false);

  const showOriginal = activeMode === "original" || activeMode === "extracted";

  // Reset mode when navigating to a different document.
  useEffect(() => {
    initialModeDoneRef.current = false;
    setActiveMode("original");
  }, [docId]);

  // Poll for translation versions when there are in-progress translations.
  // When a pending/running translation completes, invalidate the preview
  // so that the next render fetches the latest translated content.
  const { data: versions } = useQuery({
    queryKey: ["doc-translation-versions", docId],
    queryFn: () => getTranslationVersions(docId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && data.some((v) => v.status === "pending" || v.status === "running")
        ? 5000
        : false;
    },
  });

  // Set default mode once per document when translation versions first load.
  useEffect(() => {
    if (initialModeDoneRef.current) return;
    if (!versions) return;
    initialModeDoneRef.current = true;
    if (versions.some((v) => v.status === "available")) {
      setActiveMode("translation");
    }
  }, [versions]);

  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId !== undefined) return;
    if (showOriginal) return;
    if (versions.some((v) => v.status === "pending" || v.status === "running")) {
      hadInProgressRef.current = true;
      return;
    }
    if (hadInProgressRef.current) {
      hadInProgressRef.current = false;
      qc.invalidateQueries({ queryKey: ["doc-preview", docId] });
    }
  }, [versions, selectedVersionId, showOriginal, docId, qc]);

  const {
    data: preview,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["doc-preview", docId, selectedVersionId, showOriginal],
    queryFn: () =>
      measurePerformance("preview.load", () =>
        getPreview(docId, selectedVersionId, showOriginal),
      ),
    staleTime: 2 * 60_000,
  });

  const availableModes = useMemo<ViewMode[]>(() => {
    const modes: ViewMode[] = ["original"];
    if (preview?.snippet) modes.push("extracted");
    if (versions?.some((v) => v.status === "available")) modes.push("translation");
    return modes;
  }, [preview?.snippet, versions]);

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingShell}>
          <SkeletonRow count={8} />
        </div>
      </div>
    );
  }

  if (isError || !preview) {
    return (
      <div className={styles.page}>
        <EmptyState
          title={t.document.notFoundTitle}
          body={t.document.notFoundBody}
          action={
            <Button variant="secondary" onClick={() => void refetch()}>
              {t.document.tryAgain}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <DocumentToolbar
        preview={preview}
        selectedVersionId={selectedVersionId}
        showOriginal={showOriginal}
        availableModes={availableModes}
        activeMode={activeMode}
        onVersionChange={setSelectedVersionId}
        onShowOriginalChange={(val) => setActiveMode(val ? "original" : "translation")}
        onModeChange={setActiveMode}
      />
      {preview.has_newer_version && preview.latest_document_id && (
        <VersionBanner latestDocumentId={preview.latest_document_id} />
      )}
      <FidelityStatusBar
        activeMode={activeMode}
        translationQuality={preview.translation_quality}
        downloadUrl={getDownloadUrl(preview.document_id)}
      />
      <div className={styles.body}>
        <div className={styles.previewCol}>
          <PreviewPane
            preview={preview}
            activeMode={activeMode}
            selectedVersionId={selectedVersionId}
          />
        </div>
        <div className={styles.insightCol}>
          <InsightPane docId={docId} />
        </div>
      </div>
    </div>
  );
}
