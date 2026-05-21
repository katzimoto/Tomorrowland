import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocumentText } from "@/api/documents";
import { highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

const CHUNK_SIZE = 10_000;

interface TextPreviewProps {
  text?: string;
  docId?: string;
  translationVersionId?: string;
  showOriginal?: boolean;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function TextPreview({
  text,
  docId,
  translationVersionId,
  showOriginal,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: TextPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    setExtraChunks([]);
    setExtraTruncated(null);
    setNextOffset(CHUNK_SIZE);
  }, [docId, translationVersionId, showOriginal]);

  const baseText = docId
    ? [data?.text ?? "", ...extraChunks].join("")
    : (text ?? "");

  const { nodes: highlighted, count: matchCount } = useMemo(
    () =>
      searchQuery
        ? highlightMatches(baseText, searchQuery, activeSearchIndex, styles.match, styles.activeMatch)
        : { nodes: null, count: 0 },
    [baseText, searchQuery, activeSearchIndex],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  useEffect(() => {
    if (!searchQuery || matchCount === 0) return;
    containerRef.current
      ?.querySelector<HTMLElement>(`[data-match-index="${activeSearchIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeSearchIndex, searchQuery, matchCount]);

  if (!docId) {
    return (
      <div ref={containerRef}>
        <pre className={styles.textContent}>
          {searchQuery ? highlighted : (text || "No text content available.")}
        </pre>
      </div>
    );
  }

  if (isLoading) {
    return <div className={styles.muted}>Loading…</div>;
  }

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
    <div ref={containerRef}>
      <pre className={styles.textContent}>
        {searchQuery ? highlighted : (baseText || "No text content available.")}
      </pre>
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
