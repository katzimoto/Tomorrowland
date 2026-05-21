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
