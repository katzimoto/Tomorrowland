import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getPreview } from "@/api/documents";
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
    staleTime: 2 * 60_000,
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
