import { useCallback, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Papa from "papaparse";
import { List } from "react-window";
import { countMatches, highlightMatches } from "../highlightMatches";
import { getDocumentText } from "@/api/documents";
import styles from "./renderers.module.css";

const VIRTUALIZE_THRESHOLD = 1_000;
const ROW_HEIGHT = 32;
// Fetch up to 500 KB so most spreadsheets fit in one request.
const TABLE_FETCH_LIMIT = 500_000;

interface TablePreviewProps {
  docId?: string;
  /** Snippet fallback when docId is not provided. */
  text?: string;
  /** Column delimiter: "\t" for TSV/Excel extractions, "," for CSV. */
  delimiter?: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

function parseTable(raw: string, delimiter: string): string[][] {
  const result = Papa.parse<string[]>(raw, {
    delimiter,
    skipEmptyLines: true,
  });
  return result.data;
}

function cellMatches(cell: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return false;
  return cell.toLowerCase().includes(searchQuery.toLowerCase());
}

export function TablePreview({
  docId,
  text: snippetText = "",
  delimiter = "\t",
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: TablePreviewProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["doc-table-text", docId, delimiter],
    queryFn: () =>
      getDocumentText(docId!, { offset: 0, limit: TABLE_FETCH_LIMIT }),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });

  const rawText = docId ? (data?.text ?? "") : snippetText;
  const truncated = docId ? (data?.truncated ?? false) : false;

  const rows = useMemo(() => parseTable(rawText, delimiter), [rawText, delimiter]);

  const flatText = useMemo(() => rows.flat().join(" "), [rows]);

  // Precompute the starting flat-cell index for each row so the mapping from
  // (rowIdx, colIdx) → flatCellIdx is correct even for jagged tables.
  const rowStartIndices = useMemo(() => {
    const starts: number[] = [0];
    for (let i = 0; i < rows.length - 1; i++) {
      starts.push(starts[i] + rows[i].length);
    }
    return starts;
  }, [rows]);

  // Per-cell cumulative offsets for mapping globalActiveIndex → cell highlight.
  const cellMatchCounts = useMemo(() => {
    if (!searchQuery) return [] as number[];
    return rows.flatMap((row) => row.map((cell) => countMatches(cell, searchQuery)));
  }, [rows, searchQuery]);

  const cumulativeOffsets = useMemo(() => {
    const offsets: number[] = [0];
    for (let i = 0; i < cellMatchCounts.length - 1; i++) {
      offsets.push(offsets[i] + cellMatchCounts[i]);
    }
    return offsets;
  }, [cellMatchCounts]);

  const matchCount = useMemo(
    () => countMatches(flatText, searchQuery),
    [flatText, searchQuery],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  const getCellHighlight = useCallback(
    (rowIdx: number, colIdx: number, cell: string) => {
      if (!searchQuery || !cellMatches(cell, searchQuery)) return cell;
      const flatCellIdx = (rowStartIndices[rowIdx] ?? 0) + colIdx;
      const localIndex = activeSearchIndex - (cumulativeOffsets[flatCellIdx] ?? 0);
      const { nodes } = highlightMatches(
        cell,
        searchQuery,
        localIndex,
        styles.match,
        styles.activeMatch,
      );
      return nodes;
    },
    [rowStartIndices, searchQuery, activeSearchIndex, cumulativeOffsets],
  );

  const RowComponent = useCallback(
    ({ index, style }: { index: number; style: React.CSSProperties }) => {
      const row = rows[index + 1]; // +1 to skip the header
      return (
        <div style={style} role="row">
          {row?.map((cell, ci) => (
            <div
              key={ci}
              role="cell"
              className={`${styles.td} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}
            >
              {getCellHighlight(index + 1, ci, cell)}
            </div>
          ))}
        </div>
      );
    },
    [rows, searchQuery, getCellHighlight],
  );

  if (isLoading) {
    return <div className={styles.muted}>Loading…</div>;
  }

  if (!rows.length) {
    return <p className={styles.muted}>No table data available.</p>;
  }

  const [header, ...body] = rows;
  const isVirtualized = body.length > VIRTUALIZE_THRESHOLD;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rc: any = RowComponent;

  return (
    <>
      {truncated && (
        <div className={styles.muted} style={{ padding: "var(--space-2) var(--space-4)" }}>
          Showing first {(rawText.length / 1024).toFixed(0)} KB — download original for full file
        </div>
      )}
      <div className={styles.tableWrapper}>
        {isVirtualized ? (
          <div role="table" aria-label="Document table">
            <div role="rowgroup">
              <div role="row">
                {header.map((cell, i) => (
                  <div key={i} role="columnheader" className={styles.th}>
                    {cell}
                  </div>
                ))}
              </div>
            </div>
            <div role="rowgroup">
              <List
                rowCount={body.length}
                rowHeight={ROW_HEIGHT}
                rowComponent={rc}
                rowProps={{}}
                style={{ height: Math.min(body.length * ROW_HEIGHT, 600), width: "100%" }}
              />
            </div>
          </div>
        ) : (
          <table className={styles.table} aria-label="Document table">
            <thead>
              <tr>
                {header.map((cell, i) => (
                  <th
                    key={i}
                    scope="col"
                    className={`${styles.th} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}
                  >
                    {getCellHighlight(0, i, cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className={`${styles.td} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}
                    >
                      {getCellHighlight(ri + 1, ci, cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
