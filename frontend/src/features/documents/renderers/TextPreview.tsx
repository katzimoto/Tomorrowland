import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocumentText } from "@/api/documents";
import styles from "./renderers.module.css";

const CHUNK_SIZE = 10_000;

interface TextPreviewProps {
  text?: string;
  docId?: string;
  translationVersionId?: string;
  showOriginal?: boolean;
}

export function TextPreview({ text, docId, translationVersionId, showOriginal }: TextPreviewProps) {
  const [extraChunks, setExtraChunks] = useState<string[]>([]);
  const [extraTruncated, setExtraTruncated] = useState<boolean | null>(null);
  const [nextOffset, setNextOffset] = useState(CHUNK_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["doc-text", docId, translationVersionId, showOriginal],
    queryFn: () =>
      getDocumentText(docId!, {
        offset: 0,
        limit: CHUNK_SIZE,
        translationVersionId,
        showOriginal,
      }),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });

  // Reset accumulated pages when document identity changes
  useEffect(() => {
    setExtraChunks([]);
    setExtraTruncated(null);
    setNextOffset(CHUNK_SIZE);
  }, [docId, translationVersionId, showOriginal]);

  if (!docId) {
    return <pre className={styles.textContent}>{text || "No text content available."}</pre>;
  }

  if (isLoading) {
    return <div className={styles.muted}>Loading…</div>;
  }

  const allText = [data?.text ?? "", ...extraChunks].join("");
  const isTruncated = extraTruncated !== null ? extraTruncated : (data?.truncated ?? false);

  async function handleLoadMore() {
    if (!docId || loadingMore) return;
    setLoadingMore(true);
    try {
      const result = await getDocumentText(docId, {
        offset: nextOffset,
        limit: CHUNK_SIZE,
        translationVersionId,
        showOriginal,
      });
      setExtraChunks((prev) => [...prev, result.text]);
      setExtraTruncated(result.truncated);
      setNextOffset(result.offset + result.limit);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div>
      <pre className={styles.textContent}>{allText || "No text content available."}</pre>
      {isTruncated && (
        <button
          className={styles.loadMoreBtn}
          onClick={handleLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
