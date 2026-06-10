import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { getDocumentText } from "@/api/documents";
import { countMatches, highlightMatches } from "../highlightMatches";
import {
  finishNamedPerformanceTimer,
  startNamedPerformanceTimer,
} from "@/lib/performanceTelemetry";
import styles from "./renderers.module.css";

const CHUNK_SIZE = 10_000;
const VIRTUALIZE_THRESHOLD = 10_000;
const ROW_HEIGHT = 22;

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
  const scrollRef = useRef<HTMLDivElement>(null);
  const [extraChunks, setExtraChunks] = useState<string[]>([]);
  const [extraTruncated, setExtraTruncated] = useState<boolean | null>(null);
  const [nextOffset, setNextOffset] = useState(CHUNK_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);
  // Generation counter: incremented on every doc/version change so stale
  // in-flight "Load more" responses never write into the new document's state.
  const loadGenRef = useRef(0);

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
    loadGenRef.current += 1;
    startTransition(() => {
      setExtraChunks([]);
      setExtraTruncated(null);
      setNextOffset(CHUNK_SIZE);
    });
  }, [docId, translationVersionId, showOriginal]);

  const textLoadTimer = useRef<string | null>(null);
  useEffect(() => {
    if (!docId) return;
    textLoadTimer.current = `text-load-${Date.now()}`;
    startNamedPerformanceTimer(textLoadTimer.current);
  }, [docId, translationVersionId, showOriginal]);

  useEffect(() => {
    if (data && textLoadTimer.current) {
      finishNamedPerformanceTimer(textLoadTimer.current, "viewer.text.load", "success");
      textLoadTimer.current = null;
    }
  }, [data]);

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

  const lines = baseText ? baseText.split("\n") : [];
  const isVirtualized = lines.length > VIRTUALIZE_THRESHOLD;

  const perLineMatchCounts = useMemo(() => {
    if (!searchQuery) return lines.map(() => 0);
    return lines.map((line) => countMatches(line, searchQuery));
  }, [lines, searchQuery]);

  const cumulativeMatchOffsets = useMemo(() => {
    const offsets: number[] = [0];
    for (let i = 0; i < perLineMatchCounts.length - 1; i++) {
      offsets.push(offsets[i] + perLineMatchCounts[i]);
    }
    return offsets;
  }, [perLineMatchCounts]);

  const rowVirtualizer = useVirtualizer({
    count: isVirtualized ? lines.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  function renderLine(line: string, lineIndex: number) {
    if (searchQuery) {
      const localIndex = activeSearchIndex - (cumulativeMatchOffsets[lineIndex] ?? 0);
      const matches = highlightMatches(
        line,
        searchQuery,
        localIndex,
        styles.match,
        styles.activeMatch,
      );
      return matches.nodes || line;
    }
    return line;
  }

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
    const gen = loadGenRef.current;
    try {
      const result = await getDocumentText(docId, {
        offset: nextOffset,
        limit: CHUNK_SIZE,
        translationVersionId,
        showOriginal,
      });
      if (loadGenRef.current !== gen) return;
      setExtraChunks((prev) => [...prev, result.text]);
      setExtraTruncated(result.truncated);
      setNextOffset(result.offset + result.limit);
    } finally {
      if (loadGenRef.current === gen) setLoadingMore(false);
    }
  }

  if (isVirtualized) {
    return (
      <div ref={containerRef} className={styles.virtualContainer}>
        <div
          ref={scrollRef}
          style={{ height: Math.min(lines.length * ROW_HEIGHT, 600), width: "100%", overflow: "auto" }}
        >
          <div
            role="list"
            style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => (
              <div
                key={virtualRow.key}
                className={styles.virtualRow}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {renderLine(lines[virtualRow.index] ?? "", virtualRow.index)}
              </div>
            ))}
          </div>
        </div>
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
