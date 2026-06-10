import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { marked } from "marked";
import type { Config as DOMPurifyConfig } from "dompurify";
import DOMPurify from "dompurify";
import { getDocumentText } from "@/api/documents";
import { countMatches, highlightMatches, highlightInHtml } from "../highlightMatches";
import styles from "./renderers.module.css";

interface MarkdownPreviewProps {
  docId: string;
  /** Fallback snippet used if docId fetch is unavailable. */
  fallbackText?: string;
  showOriginal?: boolean;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if ("target" in node && (node as Element).tagName === "A") {
    const href = (node as Element).getAttribute("href") ?? "";
    if (href.startsWith("javascript:") || href.startsWith("vbscript:")) {
      (node as Element).setAttribute("href", "#");
    }
    if (!href.startsWith("#")) {
      (node as Element).setAttribute("target", "_blank");
      (node as Element).setAttribute("rel", "noopener noreferrer");
    }
  }
});

const SANITIZE_CONFIG: DOMPurifyConfig = {
  FORBID_TAGS: ["script", "style"],
};

export function MarkdownPreview({
  docId,
  fallbackText = "",
  showOriginal,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: MarkdownPreviewProps) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const renderedRef = useRef<HTMLDivElement>(null);
  const rawRef = useRef<HTMLPreElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (copyTimerRef.current) clearTimeout(copyTimerRef.current); }, []);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-text", docId, showOriginal],
    queryFn: () => getDocumentText(docId, { offset: 0, limit: 100_000, showOriginal }),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });

  const text = data?.text ?? fallbackText;

  // Total match count is derived from raw text so both modes stay in sync.
  const matchCount = useMemo(
    () => countMatches(text, searchQuery),
    [text, searchQuery],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  // Rendered HTML — includes <mark> wrappers when a search query is active.
  // Does NOT encode the activeIndex so activeSearchIndex changes don't force a
  // full re-render; the active mark is promoted via DOM class manipulation.
  const sanitizedHtml = useMemo(() => {
    if (!text) return "";
    const raw = marked.parse(text, { async: false }) as string;
    const sanitized = DOMPurify.sanitize(raw, SANITIZE_CONFIG);
    if (!searchQuery) return sanitized;
    return highlightInHtml(sanitized, searchQuery).html;
  }, [text, searchQuery]);

  // Raw-mode highlight nodes (active mark baked in via React virtual DOM).
  const rawHighlighted = useMemo(
    () =>
      searchQuery
        ? highlightMatches(text, searchQuery, activeSearchIndex, styles.match, styles.activeMatch)
        : null,
    [text, searchQuery, activeSearchIndex],
  );

  // Promote the active mark in the rendered div without re-parsing the HTML.
  useEffect(() => {
    if (mode !== "rendered" || !searchQuery || matchCount === 0) return;
    const container = renderedRef.current;
    if (!container) return;
    container.querySelectorAll<HTMLElement>(".preview-match-active").forEach((el) => {
      el.classList.remove("preview-match-active");
    });
    const el = container.querySelector<HTMLElement>(
      `[data-match-index="${activeSearchIndex}"]`,
    );
    if (el) {
      el.classList.add("preview-match-active");
      el.scrollIntoView({ block: "nearest" });
    }
  }, [mode, activeSearchIndex, searchQuery, matchCount]);

  // Scroll the active mark into view in raw mode.
  useEffect(() => {
    if (mode !== "raw" || !searchQuery || matchCount === 0) return;
    rawRef.current
      ?.querySelector<HTMLElement>(`[data-match-index="${activeSearchIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [mode, activeSearchIndex, searchQuery, matchCount]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API unavailable — silently ignore
    }
  }

  if (isLoading) {
    return <div className={styles.muted}>Loading…</div>;
  }

  if (isError && !fallbackText) {
    return <div className={styles.muted}>Failed to load document content.</div>;
  }

  return (
    <div>
      <div className={styles.markdownToolbar}>
        <button
          className={mode === "raw" ? styles.markdownToolbarBtnActive : styles.markdownToolbarBtn}
          onClick={() => setMode("raw")}
        >
          Raw
        </button>
        <button
          className={mode === "rendered" ? styles.markdownToolbarBtnActive : styles.markdownToolbarBtn}
          onClick={() => setMode("rendered")}
        >
          Rendered
        </button>
        <button
          className={styles.markdownToolbarBtn}
          onClick={handleCopy}
          aria-label="Copy raw Markdown"
          style={{ marginLeft: "auto" }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {mode === "raw" ? (
        <pre ref={rawRef} className={styles.textContent}>
          {rawHighlighted ? rawHighlighted.nodes : (text || "No content")}
        </pre>
      ) : (
        <div
          ref={renderedRef}
          className={styles.htmlContent}
          dangerouslySetInnerHTML={{ __html: sanitizedHtml || "<p>No content</p>" }}
        />
      )}
    </div>
  );
}
