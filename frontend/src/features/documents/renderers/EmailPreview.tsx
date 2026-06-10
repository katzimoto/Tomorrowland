import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocumentText } from "@/api/documents";
import { highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

const CHUNK_SIZE = 10_000;

interface EmailPreviewProps {
  docId?: string;
  /** Snippet fallback when docId is not provided. */
  text: string;
  metadata: Record<string, unknown>;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function EmailPreview({
  docId,
  text: snippetText,
  metadata,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: EmailPreviewProps) {
  const [extraChunks, setExtraChunks] = useState<string[]>([]);
  const [extraTruncated, setExtraTruncated] = useState<boolean | null>(null);
  const [nextOffset, setNextOffset] = useState(CHUNK_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadGenRef = useRef(0);
  const bodyRef = useRef<HTMLPreElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["doc-text", docId],
    queryFn: () => getDocumentText(docId!, { offset: 0, limit: CHUNK_SIZE }),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    loadGenRef.current += 1;
    setExtraChunks([]);
    setExtraTruncated(null);
    setNextOffset(CHUNK_SIZE);
  }, [docId]);

  const bodyText = docId
    ? [data?.text ?? "", ...extraChunks].join("")
    : snippetText;

  const isTruncated =
    extraTruncated !== null ? extraTruncated : (data?.truncated ?? false);

  const { nodes: bodyNodes, count: matchCount } = useMemo(
    () => highlightMatches(bodyText, searchQuery, activeSearchIndex, styles.match, styles.activeMatch),
    [bodyText, searchQuery, activeSearchIndex],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  useEffect(() => {
    if (!searchQuery || matchCount === 0) return;
    bodyRef.current
      ?.querySelector<HTMLElement>(`[data-match-index="${activeSearchIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeSearchIndex, searchQuery, matchCount]);

  async function handleLoadMore() {
    if (!docId || loadingMore) return;
    setLoadingMore(true);
    const gen = loadGenRef.current;
    try {
      const result = await getDocumentText(docId, {
        offset: nextOffset,
        limit: CHUNK_SIZE,
      });
      if (loadGenRef.current !== gen) return;
      setExtraChunks((prev) => [...prev, result.text]);
      setExtraTruncated(result.truncated);
      setNextOffset(result.offset + result.limit);
    } finally {
      if (loadGenRef.current === gen) setLoadingMore(false);
    }
  }

  if (isLoading) {
    return <div className={styles.muted}>Loading…</div>;
  }

  return (
    <div className={styles.emailWrapper}>
      <dl className={styles.emailHeaders}>
        {Boolean(metadata["from"]) && (
          <>
            <dt className={styles.emailHeaderKey}>From</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["from"])}</dd>
          </>
        )}
        {Boolean(metadata["to"]) && (
          <>
            <dt className={styles.emailHeaderKey}>To</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["to"])}</dd>
          </>
        )}
        {Boolean(metadata["cc"]) && (
          <>
            <dt className={styles.emailHeaderKey}>CC</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["cc"])}</dd>
          </>
        )}
        {Boolean(metadata["date"]) && (
          <>
            <dt className={styles.emailHeaderKey}>Date</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["date"])}</dd>
          </>
        )}
        {Boolean(metadata["subject"]) && (
          <>
            <dt className={styles.emailHeaderKey}>Subject</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["subject"])}</dd>
          </>
        )}
      </dl>
      <pre ref={bodyRef} className={styles.emailBody}>
        {searchQuery ? bodyNodes : bodyText}
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
