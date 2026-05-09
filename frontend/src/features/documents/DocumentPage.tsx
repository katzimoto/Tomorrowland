import { useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getPreview } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { DocumentToolbar } from "./DocumentToolbar";
import { PreviewPane } from "./PreviewPane";
import { InsightPane } from "./InsightPane";
import styles from "./DocumentPage.module.css";

export function DocumentPage() {
  const { docId } = useParams({ from: "/app/doc/$docId" });
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>(undefined);

  const { data: preview, isLoading, isError, refetch } = useQuery({
    queryKey: ["doc-preview", docId, selectedVersionId],
    queryFn: () => getPreview(docId, selectedVersionId),
  });

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingShell}><SkeletonRow count={8} /></div>
      </div>
    );
  }

  if (isError || !preview) {
    return (
      <div className={styles.page}>
        <EmptyState
          title="Document not found"
          body="This document may have been deleted or you may not have access."
          action={
            <Button variant="secondary" onClick={() => void refetch()}>
              Try again
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
