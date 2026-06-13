import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
}: SheetViewerProps) {
  const t = useT();
  const sheets = manifest.navigation.items as { index: number; label: string; artifact_id: string }[];
  const [activeIndex, setActiveIndex] = useState(0);
  const active = sheets[activeIndex];

  const { data: grid, isLoading } = useQuery({
    queryKey: ["preview-artifact", docId, active?.artifact_id, manifest.cache_key],
    queryFn: async (): Promise<SheetGrid> =>
      JSON.parse(await getPreviewArtifactText(docId, active!.artifact_id)) as SheetGrid,
    enabled: !!active,
    staleTime: 5 * 60_000,
  });

  const matchCount = useMemo(() => {
    if (!searchQuery || !grid) return 0;
    return grid.rows.reduce(
      (sum, row) => sum + row.reduce((s, cell) => s + countMatches(cell, searchQuery), 0),
      0,
    );
  }, [grid, searchQuery]);

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  return (
    <div className={styles.sheetWrapper} role="region" aria-label={t.preview.sheetRegion}>
      {sheets.length > 1 && (
        <div className={styles.sheetTabs} role="tablist" aria-label={t.preview.sheetTabs}>
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
            </button>
          ))}
        </div>
      )}

      {isLoading || !grid ? (
        <div className={styles.muted}>{t.preview.loading}</div>
      ) : (
        <>
          {(grid.truncated.rows || grid.truncated.cols) && (
            <div className={styles.sheetTruncatedNote} role="note">
              {t.preview.sheetTruncated}
            </div>
          )}
          <div className={styles.sheetGridScroll}>
            <table className={styles.sheetTable}>
              <tbody>
                {grid.rows.map((row, r) => (
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
