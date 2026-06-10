import { useEffect, useMemo, useRef } from "react";
import { highlightInHtml } from "../highlightMatches";
import styles from "./renderers.module.css";

interface HtmlPreviewProps {
  html: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

/** Dark-mode override injected into the iframe so HTML previews
 *  match the workspace surface instead of showing a white sheet. */
const DARK_OVERRIDE = `
<style>
  :root { color-scheme: dark; }
  html, body {
    background: #0d1117 !important;
    color: #e6edf3 !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.65;
  }
  a { color: #58a6ff; }
  h1, h2, h3, h4, h5, h6 { color: #e6edf3; }
  p { color: #8b949e; }
  p strong, b { color: #e6edf3; }
  code, pre {
    background: #161b22;
    color: #e6edf3;
    border-radius: 4px;
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  table { border-collapse: collapse; }
  th, td {
    border: 1px solid #30363d;
    padding: 6px 12px;
  }
  th { background: #161b22; }
  blockquote {
    border-left: 3px solid #30363d;
    margin: 0;
    padding-left: 12px;
    color: #8b949e;
  }
  hr { border-color: #30363d; }
  mark {
    background: rgba(210, 153, 34, 0.22);
    color: #e6edf3;
  }
  .preview-match {
    background: #fef08a;
    color: #1a1a1a;
    border-radius: 2px;
  }
  .preview-match-active {
    background: #fb923c;
    color: #fff;
    border-radius: 2px;
  }
</style>
`;

function prependDarkOverride(html: string): string {
  const headMatch = html.match(/<head[^>]*>/i);
  if (headMatch && headMatch.index !== undefined) {
    const insertAt = headMatch.index + headMatch[0].length;
    return html.slice(0, insertAt) + DARK_OVERRIDE + html.slice(insertAt);
  }
  // No <head> — prepend before everything
  return DARK_OVERRIDE + html;
}

export function HtmlPreview({
  html,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: HtmlPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Inject marks for all matches. Active mark is promoted via DOM manipulation
  // so activeSearchIndex changes don't reload the iframe.
  const { markedHtml, matchCount } = useMemo(() => {
    const base = prependDarkOverride(html ?? "");
    if (!searchQuery) return { markedHtml: base, matchCount: 0 };
    const { html: marked, count } = highlightInHtml(base, searchQuery);
    return { markedHtml: marked, matchCount: count };
  }, [html, searchQuery]);

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  function applyActiveMatch(doc: Document) {
    doc.querySelectorAll<HTMLElement>(".preview-match-active").forEach((el) => {
      el.classList.remove("preview-match-active");
    });
    if (!searchQuery || matchCount === 0) return;
    const el = doc.querySelector<HTMLElement>(
      `[data-match-index="${activeSearchIndex}"]`,
    );
    if (el) {
      el.classList.add("preview-match-active");
      el.scrollIntoView({ block: "nearest" });
    }
  }

  // After the iframe loads with new search content, highlight the first match.
  function handleIframeLoad() {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    applyActiveMatch(doc);
  }

  // When the user navigates between matches the srcDoc doesn't change, so we
  // update the active mark directly in the already-loaded iframe document.
  useEffect(() => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc?.body) return;
    applyActiveMatch(doc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSearchIndex, searchQuery, matchCount]);

  return (
    <iframe
      ref={iframeRef}
      srcDoc={markedHtml}
      sandbox="allow-same-origin"
      title="HTML document preview"
      className={styles.htmlFrame}
      onLoad={handleIframeLoad}
    />
  );
}
