import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExpertise } from "@/api/expertise";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { ExpertiseResultList } from "./ExpertiseResultList";
import styles from "./Expertise.module.css";

export function ExpertisePage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const results = useQuery({ queryKey: ["expertise", query], queryFn: () => getExpertise(query), enabled: query.trim().length > 0 });

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>Expertise map</h1><p className={styles.subtitle}>Find colleagues through document evidence. Results are not rankings or performance scores.</p></header>
      <div className={styles.body}>
        <form className={styles.searchRow} onSubmit={(event) => { event.preventDefault(); setQuery(input.trim()); }}>
          <label className="sr-only" htmlFor="expertise-query">Topic</label>
          <input id="expertise-query" value={input} onChange={(event) => setInput(event.target.value)} placeholder="e.g. incident response" />
          <Button type="submit" disabled={!input.trim()}>Find evidence</Button>
        </form>
        {results.isLoading && <p>Loading evidence…</p>}
        {results.isError && <EmptyState title="Could not load expertise evidence" body="Try again later." />}
        {!results.isLoading && !results.isError && <ExpertiseResultList hasQuery={query.trim().length > 0} results={results.data?.results ?? []} />}
      </div>
    </div>
  );
}
