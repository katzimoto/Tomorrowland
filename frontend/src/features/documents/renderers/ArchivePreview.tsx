import { useEffect, useMemo } from "react";
import { countMatches, highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

interface ArchivePreviewProps {
  text: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function ArchivePreview({ text, searchQuery = "", activeSearchIndex = 0, onMatchCountChange }: ArchivePreviewProps) {
  const filenames = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const matchCount = useMemo(
    () => countMatches(text, searchQuery),
    [text, searchQuery],
  );
  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  const { nodes: highlightedNodes } = useMemo(
    () => highlightMatches(text, searchQuery, activeSearchIndex, styles.match, styles.activeMatch),
    [text, searchQuery, activeSearchIndex],
  );

  if (!filenames.length) {
    return <p className={styles.muted}>Archive is empty.</p>;
  }

  return (
    <div>
      {searchQuery ? (
        <pre className={styles.textContent}>{highlightedNodes}</pre>
      ) : (
        <ul className={styles.archiveList} aria-label="Archive contents">
          {filenames.map((name, i) => (
            <li key={i} className={styles.archiveItem}>{name}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
