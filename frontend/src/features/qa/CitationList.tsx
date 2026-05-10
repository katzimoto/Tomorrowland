import type { QACitation } from "@/api/qa";
import { CitationCard } from "./CitationCard";
import styles from "./CitationList.module.css";

interface CitationListProps {
  citations: QACitation[];
  returnPath?: string;
}

export function CitationList({ citations, returnPath }: CitationListProps) {
  if (!citations.length) return null;

  return (
    <div className={styles.wrapper}>
      <h3 className={styles.heading}>Sources</h3>
      <ul className={styles.list}>
        {citations.map((c) => (
          <CitationCard key={c.doc_id} citation={c} returnPath={returnPath} />
        ))}
      </ul>
    </div>
  );
}
