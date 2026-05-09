import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Download, Languages, ArrowLeft } from "lucide-react";
import { getPreview, requestTranslation, getDownloadUrl } from "@/api/documents";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import { PreviewPane } from "./PreviewPane";
import { DetailsPanel } from "./DetailsPanel";
import styles from "./DocumentPage.module.css";

export function DocumentPage() {
  const { docId } = useParams({ from: "/app/doc/$docId" });
  const navigate = useNavigate();
  const { show: showToast } = useToast();

  const { data: preview, isLoading, isError } = useQuery({
    queryKey: ["doc-preview", docId],
    queryFn: () => getPreview(docId),
  });

  const translateMut = useMutation({
    mutationFn: () => requestTranslation(docId),
    onSuccess: () => showToast("success", "High-quality translation queued."),
    onError: () => showToast("error", "Failed to queue translation."),
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
          title="Document not found"
          body="This document may have been deleted or you may not have access."
          action={<Button variant="secondary" onClick={() => void navigate({ to: "/search", search: () => ({ q: "", mode: "hybrid" }) })}>Back to search</Button>}
        />
      </div>
    );
  }

  const translationVariant =
    preview.translation_quality === "high" ? "success" :
    preview.translation_quality === "fast" ? "warning" : "neutral";

  const translationLabel =
    preview.translation_quality === "high" ? "High quality" :
    preview.translation_quality === "fast" ? "Fast translation" : "Not translated";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.backBtn} onClick={() => void navigate({ to: "/search", search: () => ({ q: "", mode: "hybrid" }) })} aria-label="Back to search">
          <ArrowLeft size={18} />
        </button>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{preview.title ?? "Untitled document"}</h1>
          <Badge variant={translationVariant}>{translationLabel}</Badge>
        </div>
        <div className={styles.actions}>
          {preview.translation_quality !== "high" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => translateMut.mutate()}
              loading={translateMut.isPending}
            >
              <Languages size={14} />
              Request translation
            </Button>
          )}
          <a href={getDownloadUrl(docId)} download className={styles.downloadLink}>
            <Button variant="secondary" size="sm">
              <Download size={14} />
              Download
            </Button>
          </a>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.previewCol}>
          <PreviewPane preview={preview} />
        </div>
        <div className={styles.detailsCol}>
          <DetailsPanel docId={docId} />
        </div>
      </div>
    </div>
  );
}
