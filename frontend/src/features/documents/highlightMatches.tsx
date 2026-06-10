import type { ReactNode } from "react";

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export interface HighlightResult {
  nodes: ReactNode;
  count: number;
}

export function highlightMatches(
  text: string,
  query: string,
  activeIndex: number,
  matchClassName: string,
  activeMatchClassName: string,
): HighlightResult {
  if (!query.trim()) {
    return { nodes: text, count: 0 };
  }

  const regex = new RegExp(escapeRegex(query), "gi");
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let matchIdx = 0;
  let m: RegExpExecArray | null;

  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIndex) {
      parts.push(text.slice(lastIndex, m.index));
    }
    const idx = matchIdx;
    parts.push(
      <mark
        key={`m${idx}`}
        data-match-index={idx}
        className={idx === activeIndex ? activeMatchClassName : matchClassName}
      >
        {m[0]}
      </mark>,
    );
    matchIdx++;
    lastIndex = m.index + m[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return { nodes: <>{parts}</>, count: matchIdx };
}

export function countMatches(text: string, query: string): number {
  if (!query.trim()) return 0;
  const regex = new RegExp(escapeRegex(query), "gi");
  return (text.match(regex) ?? []).length;
}

/**
 * Inject <mark> tags into an already-sanitized HTML string without touching
 * tag internals. Returns the annotated HTML and the match count.
 *
 * Safe to use on DOMPurify- or backend-sanitized HTML where raw `>` cannot
 * appear inside attribute values.
 */
export function highlightInHtml(
  html: string,
  query: string,
): { html: string; count: number } {
  if (!query.trim()) return { html, count: 0 };
  const escaped = escapeRegex(query);
  // First alternative captures full HTML tags so we skip over them entirely;
  // second alternative captures text matches outside of tags.
  const re = new RegExp(`(<[^>]*>)|(${escaped})`, "gi");
  let idx = 0;
  const result = html.replace(re, (m, tag) => {
    if (tag !== undefined) return tag;
    return `<mark data-match-index="${idx++}" class="preview-match">${m}</mark>`;
  });
  return { html: result, count: idx };
}
