import type { ExpertiseResult as ExpertiseResultType } from "@/api/expertise";
import { Badge } from "@/components/primitives/Badge";
import styles from "./Expertise.module.css";

interface ExpertiseResultProps {
  result: ExpertiseResultType;
}

export function ExpertiseResult({ result }: ExpertiseResultProps) {
  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <div><div className={styles.name}>{result.display_name}</div><div className={styles.evidence}>{result.evidence_count} evidence item{result.evidence_count === 1 ? "" : "s"} found</div></div>
        <div className={styles.topics}>{result.topics.map((topic) => <Badge key={topic} variant="neutral">{topic}</Badge>)}</div>
      </div>
      <ol className={styles.evidenceList} aria-label={`Evidence for ${result.display_name}`}>
        {result.evidence.map((item) => <li key={`${item.doc_id}-${item.excerpt}`}><strong>{item.title}</strong><p className={styles.excerpt}>{item.excerpt}</p></li>)}
      </ol>
    </article>
  );
}
