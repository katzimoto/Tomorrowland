import type { ExpertiseResult as ExpertiseResultType } from "@/api/expertise";
import { Badge } from "@/components/primitives/Badge";
import styles from "./Expertise.module.css";

interface ExpertiseResultProps {
  result: ExpertiseResultType;
}

function displayName(result: ExpertiseResultType): string {
  return result.display_name ?? "Unknown reader";
}

export function ExpertiseResult({ result }: ExpertiseResultProps) {
  const signalEntries = [
    ["Views", result.signals.views],
    ["Annotations", result.signals.annotations],
    ["Subscriptions", result.signals.subscriptions],
  ] as const;

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <div>
          <div className={styles.name}>{displayName(result)}</div>
          <div className={styles.evidence}>{result.reason}</div>
        </div>
        <Badge variant="neutral">Evidence, not ranking</Badge>
      </div>
      <dl
        className={styles.signalList}
        aria-label={`Evidence signals for ${displayName(result)}`}
      >
        {signalEntries.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {result.top_docs.length > 0 && (
        <ul
          className={styles.evidenceList}
          aria-label={`Top document evidence for ${displayName(result)}`}
        >
          {result.top_docs.map((item) => (
            <li key={item.document_id}>
              <strong>{item.title ?? "Untitled document"}</strong>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
