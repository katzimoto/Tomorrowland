import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { getPreviewArtifactText, type PreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import { countMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

function cellMatches(cell: string, query: string): boolean {
  return Boolean(query) && countMatches(cell, query) > 0;
}

interface SheetViewerProps {
  manifest: PreviewManifest;
  docId: string;
  searchQuery?: string;
  onMatchCountChange?: (count: number) => void;
  /** Navigate to this sheet (by index) when the viewer first mounts. */
  initialSheetIndex?: number | null;
  /** Navigate to this sheet (by name) when index is absent. */
  initialSheetName?: string | null;
}

interface SheetGrid {
  name: string;
  rows: string[][];
  truncated: { rows: boolean; cols: boolean };
}

export function SheetViewer({
  manifest,
  docId,
  searchQuery = "",
  onMatchCountChange,
  initialSheetIndex = null,
  initialSheetName = null,
}: SheetViewerProps) {
  const t = useT();
  const sheets = manifest.navigation.items as {
    index: number;
    label: string;
    artifact_id: string;
  }[];
  const [activeIndex, setActiveIndex] = useState(() => {
    if (initialSheetIndex != null) {
      const idx = sheets.findIndex((s) => s.index === initialSheetIndex);
      if (idx >= 0) return idx;
    }
    if (initialSheetName != null) {
      const idx = sheets.findIndex((s) => s.label === initialSheetName);
      if (idx >= 0) return idx;
    }
    return 0;
  });

  // Fetch all sheet grids in parallel so we can count matches across
  // every sheet, not just the active one (#748).
  const sheetQueries = useQueries({
    queries: sheets.map((sheet) => ({
      queryKey: [
        "preview-artifact",
        docId,
        sheet.artifact_id,
        manifest.cache_key,
      ],
      queryFn: async (): Promise<SheetGrid> =>
        JSON.parse(
          await getPreviewArtifactText(docId, sheet.artifact_id),
        ) as SheetGrid,
      enabled: !!sheet,
      staleTime: 5 * 60_000,
    })),
  });

  const isLoading = sheetQueries.some((q) => q.isLoading);
  const activeGrid = sheetQueries[activeIndex]?.data;

  // Per-sheet match counts for tab badges.
  // Recomputing every render is cheap — sheet grids are small and the
  // counts only change when searchQuery or query data changes.
  const sheetMatchCounts = sheetQueries.map((q) => {
    if (!searchQuery || !q.data) return 0;
    return q.data.rows.reduce(
      (sum, row) =>
        sum + row.reduce((s, cell) => s + countMatches(cell, searchQuery), 0),
      0,
    );
  });

  // Total match count across all sheets.
  const matchCount = useMemo(
    () => sheetMatchCounts.reduce((sum, c) => sum + c, 0),
    [sheetMatchCounts],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  return (
    <div
      className={styles.sheetWrapper}
      role="region"
      aria-label={t.preview.sheetRegion}
    >
      {sheets.length > 1 && (
        <div
          className={styles.sheetTabs}
          role="tablist"
          aria-label={t.preview.sheetTabs}
        >
          {sheets.map((sheet, idx) => (
            <button
              key={sheet.artifact_id}
              type="button"
              role="tab"
              aria-selected={idx === activeIndex}
              className={styles.sheetTab}
              onClick={() => setActiveIndex(idx)}
            >
              {sheet.label}
              {sheetMatchCounts[idx] > 0 && (
                <span className={styles.sheetTabBadge}>
                  {sheetMatchCounts[idx]}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {isLoading || !activeGrid ? (
        <div className={styles.muted}>{t.preview.loading}</div>
      ) : (
        <>
          {(activeGrid.truncated.rows || activeGrid.truncated.cols) && (
            <div className={styles.sheetTruncatedNote} role="note">
              {t.preview.sheetTruncated}
            </div>
          )}
          <div className={styles.sheetGridScroll}>
            <table className={styles.sheetTable}>
              <tbody>
                {activeGrid.rows.map((row, r) => (
                  <tr key={r}>
                    <td className={styles.sheetRowHeader}>{r + 1}</td>
                    {row.map((cell, c) => (
                      <td
                        key={c}
                        className={`${styles.sheetCell} ${
                          cellMatches(cell, searchQuery) ? styles.match : ""
                        }`}
                        title={cell}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
