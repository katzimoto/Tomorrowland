import type { ExpertiseResult as ExpertiseResultType } from "@/api/expertise";
import { EmptyState } from "@/components/primitives/EmptyState";
import { ExpertiseResult } from "./ExpertiseResult";
import styles from "./Expertise.module.css";

interface ExpertiseResultListProps {
  results: ExpertiseResultType[];
  hasQuery: boolean;
}

export function ExpertiseResultList({ results, hasQuery }: ExpertiseResultListProps) {
  if (!hasQuery) return <EmptyState title="Search evidence" body="Enter a topic to find people connected to matching document evidence." />;
  if (results.length === 0) return <EmptyState title="No evidence found" body="Try a broader topic or different wording." />;
  return <ul className={styles.list}>{results.map((result) => <li key={result.user_id}><ExpertiseResult result={result} /></li>)}</ul>;
}
