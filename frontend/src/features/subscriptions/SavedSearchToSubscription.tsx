import { SavedSearches } from "@/features/search/SavedSearches";
import type { SubscriptionWrite } from "@/api/subscriptions";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import styles from "./SubscriptionsPage.module.css";

interface SavedSearchToSubscriptionProps {
  onSelect: (values: SubscriptionWrite) => void;
}

export function SavedSearchToSubscription({ onSelect }: SavedSearchToSubscriptionProps) {
  return (
    <section className={styles.savedBox} aria-labelledby="saved-searches-title">
      <div className={styles.sectionHeader}>
        <h2 id="saved-searches-title">Saved searches</h2>
        <Badge variant="neutral">Search templates</Badge>
      </div>
      <ul className={styles.savedList}>
        {SavedSearches.map((search) => (
          <li key={search.id} className={styles.savedRow}>
            <div><strong>{search.name}</strong><span>{search.query}</span></div>
            <Button type="button" size="sm" variant="secondary" onClick={() => onSelect({ name: search.name, query: search.query, similarity_threshold: 0.75, enabled: true })}>Subscribe</Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
