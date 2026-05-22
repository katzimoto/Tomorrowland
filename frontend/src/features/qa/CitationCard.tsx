import { Link } from "@tanstack/react-router";
import type { QACitation } from "@/api/qa";
import styles from "./CitationCard.module.css";

interface CitationCardProps {
  citation: QACitation;
}

export function CitationCard({
  citation,
}: CitationCardProps) {
  return (
    <li className={styles.card}>
      <Link
        to="/doc/$docId"
        params={{ docId: citation.document_id }}
        search={{}}
        className={styles.title}
      >
        {citation.doc_title || citation.document_id}
      </Link>
      {citation.chunk_text && (
        <p className={styles.chunk}>{citation.chunk_text}</p>
      )}
      <span className={styles.score}>
        Relevance: {(citation.score * 100).toFixed(0)}%
      </span>
    </li>
  );
}
