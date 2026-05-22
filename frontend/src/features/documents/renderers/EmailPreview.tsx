import { useEffect, useMemo } from "react";
import { highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

interface EmailPreviewProps {
  text: string;
  metadata: Record<string, unknown>;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function EmailPreview({ text, metadata, searchQuery = "", activeSearchIndex = 0, onMatchCountChange }: EmailPreviewProps) {
  const { nodes: bodyNodes, count: matchCount } = useMemo(
    () => highlightMatches(text, searchQuery, activeSearchIndex, styles.match, styles.activeMatch),
    [text, searchQuery, activeSearchIndex],
  );
  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);
  return (
    <div className={styles.emailWrapper}>
      <dl className={styles.emailHeaders}>
        {Boolean(metadata["from"]) && (
          <>
            <dt className={styles.emailHeaderKey}>From</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["from"])}</dd>
          </>
        )}
        {Boolean(metadata["to"]) && (
          <>
            <dt className={styles.emailHeaderKey}>To</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["to"])}</dd>
          </>
        )}
        {Boolean(metadata["subject"]) && (
          <>
            <dt className={styles.emailHeaderKey}>Subject</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["subject"])}</dd>
          </>
        )}
      </dl>
      <pre className={styles.emailBody}>{searchQuery ? bodyNodes : text}</pre>
    </div>
  );
}
