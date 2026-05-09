import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { search, type SearchFilters, type SearchMode } from "@/api/search";
import { SearchInput } from "@/components/primitives/SearchInput";
import { Button } from "@/components/primitives/Button";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { FilterPanel } from "./FilterPanel";
import { ResultRow } from "./ResultRow";
import styles from "./SearchPage.module.css";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "keyword", label: "Keyword" },
  { value: "semantic", label: "Semantic" },
];

export function SearchPage() {
  const routeSearch = useSearch({ from: "/app/search" });
  const navigate = useNavigate();
  const { show: showToast } = useToast();

  const initialQ = typeof routeSearch.q === "string" ? routeSearch.q : "";
  const initialMode = (routeSearch.mode as SearchMode) ?? "hybrid";

  const [inputValue, setInputValue] = useState(initialQ);
  const [submittedQuery, setSubmittedQuery] = useState(initialQ);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [filters, setFilters] = useState<SearchFilters>({});
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut: "/" focuses search input
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (
        e.key === "/" &&
        target.tagName !== "INPUT" &&
        target.tagName !== "TEXTAREA" &&
        !target.isContentEditable
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function submitSearch(q: string = inputValue, currentMode: SearchMode = mode) {
    setSubmittedQuery(q);
    void navigate({ to: "/search", search: () => ({ q, mode: currentMode }) });
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ["search", submittedQuery, mode, filters],
    queryFn: () => search(submittedQuery, mode, filters, 20),
    enabled: submittedQuery.trim().length > 0,
  });

  useEffect(() => {
    if (isError) showToast("error", "Search failed. Check that the backend is reachable.");
  }, [isError, showToast]);

  // Active filter chips
  const activeChips: Array<{ label: string; remove: () => void }> = [];
  (filters.file_type ?? []).forEach((ft) => {
    const label = ft.split("/").pop() ?? ft;
    activeChips.push({ label, remove: () => setFilters((f) => ({ ...f, file_type: f.file_type?.filter((v) => v !== ft) || undefined })) });
  });
  (filters.translation_quality ?? []).forEach((tq) => {
    activeChips.push({ label: tq === "fast" ? "Fast translation" : "High quality", remove: () => setFilters((f) => ({ ...f, translation_quality: f.translation_quality?.filter((v) => v !== tq) || undefined })) });
  });

  const showResults = submittedQuery.trim().length > 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Search</h1>
        <div className={styles.searchRow}>
          <SearchInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={() => submitSearch()}
            autoFocus
            // Pass ref via a wrapper pattern — SearchInput forwards to input
          />
          <Button onClick={() => submitSearch()} disabled={!inputValue.trim()}>
            Search
          </Button>
        </div>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.modeGroup} role="group" aria-label="Search mode">
          {MODES.map(({ value, label }) => (
            <button
              key={value}
              className={`${styles.modeBtn} ${mode === value ? styles.modeBtnActive : ""}`}
              onClick={() => { setMode(value); if (submittedQuery) submitSearch(inputValue, value); }}
              aria-pressed={mode === value}
            >
              {label}
            </button>
          ))}
        </div>
        {data && (
          <span className={styles.resultCount}>
            {data.total.toLocaleString()} result{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {activeChips.length > 0 && (
        <div className={styles.activeFilters} aria-label="Active filters">
          {activeChips.map((chip, i) => (
            <span key={i} className={styles.filterChip}>
              {chip.label}
              <button className={styles.filterChipRemove} onClick={chip.remove} aria-label={`Remove filter: ${chip.label}`}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className={styles.body}>
        <FilterPanel filters={filters} onChange={setFilters} />

        <div className={styles.results}>
          <div className={styles.resultsList} role="list" aria-label="Search results" aria-live="polite">
            {isLoading && <SkeletonRow count={6} />}

            {isError && !isLoading && (
              <EmptyState
                title="Search unavailable"
                body="The search backend is not reachable. Check the server and try again."
                action={<Button variant="secondary" onClick={() => submitSearch()}>Retry</Button>}
              />
            )}

            {!isLoading && !isError && showResults && data?.results.length === 0 && (
              <EmptyState
                title="No results found"
                body="No accessible documents match your query. Try different terms or remove filters."
              />
            )}

            {!isLoading && !isError && !showResults && (
              <EmptyState
                title="Start searching"
                body="Type a query above and press Enter or Search."
              />
            )}

            {!isLoading && !isError && data?.results.map((result) => (
              <ResultRow
                key={result.doc_id}
                result={result}
                onClick={() => void navigate({ to: "/doc/$docId", params: { docId: result.doc_id } })}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
