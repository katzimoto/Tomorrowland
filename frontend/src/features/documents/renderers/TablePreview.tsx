import styles from "./renderers.module.css";

interface TablePreviewProps {
  text: string;
  searchQuery?: string;
}

export function TablePreview({ text, searchQuery = "" }: TablePreviewProps) {
  const rows = text
    .split("\n")
    .filter(Boolean)
    .map((row) => row.split("\t"));

  if (!rows.length) {
    return <p className={styles.muted}>No table data available.</p>;
  }

  function cellMatches(cell: string): boolean {
    if (!searchQuery.trim()) return false;
    return cell.toLowerCase().includes(searchQuery.toLowerCase());
  }

  const [header, ...body] = rows;
  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {header.map((cell, i) => (
              <th key={i} className={`${styles.th} ${cellMatches(cell) ? styles.match : ""}`}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} className={`${styles.td} ${cellMatches(cell) ? styles.match : ""}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
