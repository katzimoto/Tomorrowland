import { Link } from "@tanstack/react-router";
import type { QACitation } from "@/api/qa";
import styles from "./CitationCard.module.css";

interface CitationCardProps {
  citation: QACitation;
  returnPath?: string;
}

export function CitationCard({ citation, returnPath = "/qa" }: CitationCardProps) {
  return (
    <li className={styles.card}>
      <Link
        to="/doc/$docId"
        params={{ docId: citation.doc_id }}
        search={{ return: returnPath } as Record<string, string>}
        className={styles.title}
      >
        {citation.doc_title || citation.doc_id}
      </Link>
      {citation.chunk_text && (
        <p className={styles.chunk}>{citation.chunk_text}</p>
      )}
      <span className={styles.score}>Relevance: {(citation.score * 100).toFixed(0)}%</span>
    </li>
  );
}
