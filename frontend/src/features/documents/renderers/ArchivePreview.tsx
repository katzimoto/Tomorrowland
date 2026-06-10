import { useEffect, useMemo } from "react";
import { countMatches, highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

interface ArchivePreviewProps {
  text: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function ArchivePreview({
  text,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: ArchivePreviewProps) {
  const filenames = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  // Compute per-filename cumulative offsets so the global activeIndex maps to
  // the correct local index within each filename (same pattern as TextPreview).
  const perFileMatchCounts = useMemo(() => {
    if (!searchQuery) return filenames.map(() => 0);
    return filenames.map((name) => countMatches(name, searchQuery));
  }, [filenames, searchQuery]);

  const cumulativeOffsets = useMemo(() => {
    const offsets: number[] = [0];
    for (let i = 0; i < perFileMatchCounts.length - 1; i++) {
      offsets.push(offsets[i] + perFileMatchCounts[i]);
    }
    return offsets;
  }, [perFileMatchCounts]);

  const matchCount = useMemo(
    () => perFileMatchCounts.reduce((sum, n) => sum + n, 0),
    [perFileMatchCounts],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  if (!filenames.length) {
    return <p className={styles.muted}>Archive is empty.</p>;
  }

  return (
    <ul className={styles.archiveList} aria-label="Archive contents">
      {filenames.map((name, i) => {
        if (searchQuery && perFileMatchCounts[i] > 0) {
          const localIndex = activeSearchIndex - (cumulativeOffsets[i] ?? 0);
          const { nodes } = highlightMatches(
            name,
            searchQuery,
            localIndex,
            styles.match,
            styles.activeMatch,
          );
          return (
            <li key={i} className={styles.archiveItem}>
              {nodes}
            </li>
          );
        }
        return (
          <li key={i} className={styles.archiveItem}>
            {name}
          </li>
        );
      })}
    </ul>
  );
}
