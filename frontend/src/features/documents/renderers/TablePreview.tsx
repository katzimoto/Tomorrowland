import { useCallback, useEffect, useMemo } from "react";
import { List } from "react-window";
import { countMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

const VIRTUALIZE_THRESHOLD = 1_000;
const ROW_HEIGHT = 32;

interface TablePreviewProps {
  text: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

function cellMatches(cell: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return false;
  return cell.toLowerCase().includes(searchQuery.toLowerCase());
}

export function TablePreview({ text, searchQuery = "", onMatchCountChange }: TablePreviewProps) {
  const matchCount = useMemo(
    () => countMatches(text, searchQuery),
    [text, searchQuery],
  );
  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  const rows = text
    .split("\n")
    .filter(Boolean)
    .map((row) => row.split("\t"));

  const RowComponent = useCallback(
    ({ index, style }: { index: number; style: React.CSSProperties }) => (
      <div style={style} role="row">
        {rows[index + 1]?.map((cell, ci) => (
          <div key={ci} role="cell" className={`${styles.td} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}>
            {cell}
          </div>
        ))}
      </div>
    ),
    [rows, searchQuery],
  );

  if (!rows.length) {
    return <p className={styles.muted}>No table data available.</p>;
  }

  const [header, ...body] = rows;
  const isVirtualized = body.length > VIRTUALIZE_THRESHOLD;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rc: any = RowComponent;

  if (isVirtualized) {
    return (
      <div className={styles.tableWrapper}>
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
      </div>
    );
  }

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table} aria-label="Document table">
        <thead>
          <tr>
            {header.map((cell, i) => (
              <th key={i} scope="col" className={`${styles.th} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} className={`${styles.td} ${cellMatches(cell, searchQuery) ? styles.match : ""}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
