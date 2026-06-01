import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { X } from "lucide-react";
import { search, type SearchFilters, type SearchMode } from "@/api/search";
import { getPreview } from "@/api/documents";
import { SearchInput } from "@/components/primitives/SearchInput";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import {
  measurePerformance,
  recordPerformanceEvent,
  startPerformanceTimer,
} from "@/lib/performanceTelemetry";
import type { SearchResult } from "@/api/search";
import { FilterPanel } from "./FilterPanel";
import { ResultRow } from "./ResultRow";
import styles from "./SearchPage.module.css";

/**
 * Serialize the full search state into URL query params. Shared by explicit
 * submit and the debounced instant search so the URL always carries the
 * complete state (query, mode, filters); otherwise syncing state back from the
 * URL would wipe filters/mode that were only partially written.
 */
function buildSearchParams(
  q: string,
  searchMode: SearchMode,
  searchFilters: SearchFilters,
): Record<string, string> {
  const params: Record<string, string> = { q, mode: searchMode };
  if (searchFilters.file_type?.length) {
    params.file_type = searchFilters.file_type.join(",");
  }
  if (searchFilters.tags?.length) {
    params.tags = searchFilters.tags.join(",");
  }
  if (searchFilters.source?.length) {
    params.source = searchFilters.source.join(",");
  }
  if (searchFilters.file_extension?.length) {
    params.file_extension = searchFilters.file_extension.join(",");
  }
  if (searchFilters.sort_by && searchFilters.sort_by !== "relevance") {
    params.sort_by = searchFilters.sort_by;
  }
  return params;
}

export function SearchPage() {
  const t = useT();
  const routeSearch = useSearch({ from: "/app/search" });
  const navigate = useNavigate();
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();

  const MODES: { value: SearchMode; label: string }[] = [
    { value: "hybrid", label: t.search.modeHybrid },
    { value: "keyword", label: t.search.modeKeyword },
    { value: "semantic", label: t.search.modeSemantic },
  ];

  // Seed state from the URL once on mount. The debounced search and explicit
  // submit keep the URL in sync afterward (see buildSearchParams), so a refresh
  // restores the query, mode, and filters.
  const initialExtra = routeSearch as Record<string, unknown>;
  const initialQ = typeof routeSearch.q === "string" ? routeSearch.q : "";
  const initialMode = (routeSearch.mode as SearchMode) ?? "hybrid";
  const initialFilters: SearchFilters = {};
  if (typeof initialExtra.file_type === "string" && initialExtra.file_type) {
    initialFilters.file_type = (initialExtra.file_type as string).split(",");
  }
  if (typeof initialExtra.tags === "string" && initialExtra.tags) {
    initialFilters.tags = (initialExtra.tags as string).split(",");
  }
  if (typeof initialExtra.source === "string" && initialExtra.source) {
    initialFilters.source = (initialExtra.source as string).split(",");
  }
  if (typeof initialExtra.file_extension === "string" && initialExtra.file_extension) {
    initialFilters.file_extension = (initialExtra.file_extension as string).split(",");
  }
  if (typeof initialExtra.sort_by === "string") {
    initialFilters.sort_by = initialExtra.sort_by as SearchFilters["sort_by"];
  }

  const [inputValue, setInputValue] = useState(initialQ);
  const [submittedQuery, setSubmittedQuery] = useState(initialQ);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [filters, setFilters] = useState<SearchFilters>(initialFilters);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [previewResult, setPreviewResult] = useState<SearchResult | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const finishFirstResultTimer = useRef<(() => number) | null>(null);
  const resultsListRef = useRef<HTMLDivElement>(null);

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

  function submitSearch(
    q: string = inputValue,
    currentMode: SearchMode = mode,
    currentFilters: SearchFilters = filters,
  ) {
    finishFirstResultTimer.current = q.trim() ? startPerformanceTimer() : null;
    resetSearchWorkflow();
    setSubmittedQuery(q);
    void navigate({
      to: "/search",
      search: () =>
        buildSearchParams(q, currentMode, currentFilters) as { q: string; mode: string },
    });
  }

  // Debounce instant search — fires 350ms after the user stops typing.
  // Also syncs URL so refreshing the page preserves search state.
  // Does NOT reset preview; explicit submit (Enter/button) handles those.
  useEffect(() => {
    const q = inputValue.trim();
    if (q.length < 2) return;
    const id = setTimeout(() => {
      setSubmittedQuery(q);
      // Write the full state (q + mode + filters) so syncing back from the URL
      // doesn't drop filters/mode that aren't otherwise persisted there.
      void navigate({
        to: "/search",
        search: () => buildSearchParams(q, mode, filters) as { q: string; mode: string },
        replace: true,
      });
    }, 350);
    return () => clearTimeout(id);
  }, [inputValue, mode, filters, navigate]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ["search", submittedQuery, mode, filters],
    queryFn: () =>
      measurePerformance("search.request", () =>
        search(submittedQuery, mode, filters, 20)
      ),
    enabled: submittedQuery.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 45_000,
  });

  function prefetchPreview(docId: string) {
    void queryClient.prefetchQuery({
      queryKey: ["doc-preview", docId, undefined],
      queryFn: () => getPreview(docId),
      staleTime: 2 * 60_000,
    });
  }

  useEffect(() => {
    if (isError) {
      if (finishFirstResultTimer.current) {
        recordPerformanceEvent(
          "search.firstResult",
          finishFirstResultTimer.current(),
          "error"
        );
        finishFirstResultTimer.current = null;
      }
      showToast("error", t.search.failedToast);
    }
  }, [isError, showToast, t]);

  useEffect(() => {
    if (!data || !finishFirstResultTimer.current) return;
    if (data.results.length > 0) {
      recordPerformanceEvent(
        "search.firstResult",
        finishFirstResultTimer.current()
      );
      finishFirstResultTimer.current = null;
    }
  }, [data]);

  const results = data?.results ?? [];
  const activeSelectedIndex = Math.min(
    selectedIndex,
    Math.max(results.length - 1, 0)
  );
  const selectedResult = results[activeSelectedIndex];

  useEffect(() => {
    if (!selectedResult) return;
    document
      .getElementById(`search-result-${selectedResult.document_id}`)
      ?.scrollIntoView?.({
        block: "nearest",
      });
  }, [selectedResult]);

  function resultOptionId(docId?: string) {
    return docId ? `search-result-${docId}` : undefined;
  }

  function resetSearchWorkflow() {
    setSelectedIndex(0);
    setPreviewResult(null);
  }

  function openResult(result: SearchResult | undefined = selectedResult) {
    if (!result) return;
    void navigate({
      to: "/doc/$docId",
      params: { docId: result.document_id },
    });
  }

  function closePreview() {
    setPreviewResult(null);
    window.setTimeout(() => resultsListRef.current?.focus(), 0);
  }

  function handleResultsKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (previewResult && event.key === "Escape") {
      event.preventDefault();
      closePreview();
      return;
    }

    if (results.length === 0) return;

    if (event.key === "ArrowDown" || event.key.toLowerCase() === "j") {
      event.preventDefault();
      setSelectedIndex((index) => Math.min(index + 1, results.length - 1));
      return;
    }

    if (event.key === "ArrowUp" || event.key.toLowerCase() === "k") {
      event.preventDefault();
      setSelectedIndex((index) => Math.max(index - 1, 0));
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      openResult();
      return;
    }

    if (event.key === " ") {
      event.preventDefault();
      setPreviewResult(selectedResult ?? null);
    }
  }

  const activeChips: Array<{ label: string; remove: () => void }> = [];
  (filters.file_type ?? []).forEach((ft) => {
    const label = ft.split("/").pop() ?? ft;
    activeChips.push({
      label,
      remove: () => {
        resetSearchWorkflow();
        setFilters((f) => ({
          ...f,
          file_type: f.file_type?.filter((v) => v !== ft) || undefined,
        }));
      },
    });
  });
  (filters.translation_quality ?? []).forEach((tq) => {
    activeChips.push({
      label: tq === "fast" ? t.filters.transFast : t.filters.transHigh,
      remove: () => {
        resetSearchWorkflow();
        setFilters((f) => ({
          ...f,
          translation_quality:
            f.translation_quality?.filter((v) => v !== tq) || undefined,
        }));
      },
    });
  });
  const showResults = submittedQuery.trim().length > 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t.search.title}</h1>
        <div className={styles.searchRow}>
          <SearchInput
            ref={searchInputRef}
            value={inputValue}
            onChange={setInputValue}
            onSubmit={() => submitSearch()}
            autoFocus
          />
          <Button onClick={() => submitSearch()} disabled={!inputValue.trim()}>
            {t.search.button}
          </Button>
        </div>
      </header>

      <div className={styles.toolbar}>
        <div
          className={styles.modeGroup}
          role="group"
          aria-label={t.search.modeGroup}
        >
          {MODES.map(({ value, label }) => (
            <button
              key={value}
              className={`${styles.modeBtn} ${
                mode === value ? styles.modeBtnActive : ""
              }`}
              onClick={() => {
                setMode(value);
                if (submittedQuery) submitSearch(inputValue, value);
              }}
              aria-pressed={mode === value}
            >
              {label}
            </button>
          ))}
        </div>
        {data && (
          <span className={styles.resultCount}>
            {t.search.resultCount(data.total)}
          </span>
        )}
      </div>

      {activeChips.length > 0 && (
        <div
          className={styles.activeFilters}
          aria-label={t.search.activeFilters}
        >
          {activeChips.map((chip, i) => (
            <span key={i} className={styles.filterChip}>
              {chip.label}
              <button
                className={styles.filterChipRemove}
                onClick={chip.remove}
                aria-label={t.search.removeFilter(chip.label)}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className={styles.body}>
        <FilterPanel
          filters={filters}
          facets={data?.facets ?? {}}
          onChange={(nextFilters) => {
            resetSearchWorkflow();
            setFilters(nextFilters);
          }}
        />

        <div className={styles.results}>
          <div
            ref={resultsListRef}
            className={styles.resultsList}
            role="listbox"
            aria-label={t.search.resultsLabel}
            aria-live="polite"
            aria-busy={isFetching}
            aria-activedescendant={resultOptionId(selectedResult?.document_id)}
            aria-describedby="search-keyboard-help"
            tabIndex={0}
            onKeyDown={handleResultsKeyDown}
          >
            <p id="search-keyboard-help" className={styles.keyboardHelp}>
              {t.search.keyboardHelp}
            </p>
            {isLoading && <SkeletonRow count={6} />}
            {isFetching && !isLoading && (
              <div className={styles.refreshing} role="status">
                Updating results…
              </div>
            )}

            {isError && !isLoading && (
              <EmptyState
                title={t.search.unavailableTitle}
                body={t.search.unavailableBody}
                action={
                  <Button variant="secondary" onClick={() => submitSearch()}>
                    {t.search.retry}
                  </Button>
                }
              />
            )}

            {!isLoading &&
              !isError &&
              showResults &&
              data?.results.length === 0 && (
                <EmptyState
                  title={t.search.noResultsTitle}
                  body={t.search.noResultsBody}
                />
              )}

            {!isLoading && !isError && !showResults && (
              <EmptyState
                title={t.search.emptyTitle}
                body={t.search.emptyBody}
              />
            )}

            {!isLoading &&
              !isError &&
              results.map((result, index) => (
                <ResultRow
                  key={result.document_id}
                  id={resultOptionId(result.document_id)}
                  result={result}
                  selected={index === activeSelectedIndex}
                  onSelect={() => setSelectedIndex(index)}
                  onPreview={() => setPreviewResult(result)}
                  onClick={() => openResult(result)}
                  onPrefetch={() => prefetchPreview(result.document_id)}
                />
              ))}
          </div>
        </div>
      </div>

      <Dialog
        open={previewResult !== null}
        onClose={closePreview}
        title={previewResult?.title ?? t.search.quickPreviewTitle}
        width="680px"
      >
        {previewResult && (
          <div className={styles.previewBody}>
            <p className={styles.previewMeta}>
              {previewResult.source_label} · {previewResult.mime_type}
            </p>
            <p className={styles.previewSnippet}>{previewResult.snippet}</p>
            {previewResult.tags.length > 0 && (
              <p className={styles.previewMeta}>
                {previewResult.tags.join(", ")}
              </p>
            )}
            <div className={styles.previewActions}>
              <Button onClick={() => openResult(previewResult)}>
                {t.search.openSelected}
              </Button>
              <Button variant="secondary" onClick={closePreview}>
                {t.search.closePreview}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
