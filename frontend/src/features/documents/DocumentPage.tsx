import { useEffect, useRef, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getPreview, getTranslationVersions } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import { DocumentToolbar } from "./DocumentToolbar";
import { PreviewPane } from "./PreviewPane";
import { InsightPane } from "./InsightPane";
import styles from "./DocumentPage.module.css";

export function DocumentPage() {
  const t = useT();
  const { docId } = useParams({ from: "/app/doc/$docId" });
  const [selectedVersionId, setSelectedVersionId] = useState<
    string | undefined
  >(undefined);
  const qc = useQueryClient();
  const hadInProgressRef = useRef(false);

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

  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId !== undefined) return;
    if (versions.some((v) => v.status === "pending" || v.status === "running")) {
      hadInProgressRef.current = true;
      return;
    }
    if (hadInProgressRef.current) {
      hadInProgressRef.current = false;
      qc.invalidateQueries({ queryKey: ["doc-preview", docId] });
    }
  }, [versions, selectedVersionId, docId, qc]);

  const {
    data: preview,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["doc-preview", docId, selectedVersionId],
    queryFn: () =>
      measurePerformance("preview.load", () =>
        getPreview(docId, selectedVersionId),
      ),
  });

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
        onVersionChange={setSelectedVersionId}
      />
      <div className={styles.body}>
        <div className={styles.previewCol}>
          <PreviewPane preview={preview} />
        </div>
        <div className={styles.insightCol}>
          <InsightPane docId={docId} />
        </div>
      </div>
    </div>
  );
}
