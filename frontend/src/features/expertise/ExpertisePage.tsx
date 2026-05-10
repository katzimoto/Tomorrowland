import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExpertise } from "@/api/expertise";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useT } from "@/i18n/index";
import { ExpertiseResultList } from "./ExpertiseResultList";
import styles from "./Expertise.module.css";

export function ExpertisePage() {
  const t = useT();
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const results = useQuery({ queryKey: ["expertise", query], queryFn: () => getExpertise(query), enabled: query.trim().length > 0 });

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1 className={styles.title}>{t.expertise.title}</h1><p className={styles.subtitle}>{t.expertise.subtitle}</p></header>
      <div className={styles.body}>
        <form className={styles.searchRow} onSubmit={(event) => { event.preventDefault(); setQuery(input.trim()); }}>
          <label className="sr-only" htmlFor="expertise-query">{t.expertise.topicLabel}</label>
          <input id="expertise-query" value={input} onChange={(event) => setInput(event.target.value)} placeholder={t.expertise.placeholder} />
          <Button type="submit" disabled={!input.trim()}>{t.expertise.findBtn}</Button>
        </form>
        {results.isLoading && <p>{t.expertise.loading}</p>}
        {results.isError && <EmptyState title={t.expertise.failedTitle} body={t.expertise.failedBody} />}
        {!results.isLoading && !results.isError && <ExpertiseResultList hasQuery={query.trim().length > 0} results={results.data ?? []} />}
      </div>
    </div>
  );
}
