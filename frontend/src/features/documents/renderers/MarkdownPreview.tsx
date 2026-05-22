import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { marked } from "marked";
import type { Config as DOMPurifyConfig } from "dompurify";
import DOMPurify from "dompurify";
import { getDocumentText } from "@/api/documents";
import styles from "./renderers.module.css";

interface MarkdownPreviewProps {
  docId: string;
  /** Fallback snippet used if docId fetch is unavailable. */
  fallbackText?: string;
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

export function MarkdownPreview({ docId, fallbackText = "" }: MarkdownPreviewProps) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-text", docId],
    queryFn: () => getDocumentText(docId, { offset: 0, limit: 100_000 }),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });

  const text = data?.text ?? fallbackText;

  const html = useMemo(() => {
    if (!text) return "";
    const raw = marked.parse(text, { async: false }) as string;
    return DOMPurify.sanitize(raw, SANITIZE_CONFIG);
  }, [text]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
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
        <pre className={styles.textContent}>{text || "No content"}</pre>
      ) : (
        <div
          className={styles.htmlContent}
          dangerouslySetInnerHTML={{ __html: html || "<p>No content</p>" }}
        />
      )}
    </div>
  );
}
