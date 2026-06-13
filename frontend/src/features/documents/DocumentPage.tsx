import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getDownloadUrl, getPreview, getTranslationVersions } from "@/api/documents";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useT } from "@/i18n/index";
import { measurePerformance } from "@/lib/performanceTelemetry";
import { DocumentToolbar } from "./DocumentToolbar";
import { DocumentSearchBar } from "./DocumentSearchBar";
import { FidelityStatusBar } from "./FidelityStatusBar";
import { PreviewPane } from "./PreviewPane";
import { ParentContextBanner } from "./ParentContextBanner";
import { RendererStatusBadge } from "./RendererStatusBadge";
import { InsightPane } from "./InsightPane";
import { VersionBanner } from "./VersionBanner";
import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./DocumentPage.module.css";

export function DocumentPage() {
  const t = useT();
  const { docId } = useParams({ from: "/app/doc/$docId" });
  const [selectedVersionId, setSelectedVersionId] = useState<
    string | undefined
  >(undefined);
  const [activeMode, setActiveMode] = useState<ViewMode>("original");
  const [imageZoom, setImageZoom] = useState<number | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [rawQuery, setRawQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [matchCount, setMatchCount] = useState(0);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const initialModeDoneRef = useRef(false);
  const qc = useQueryClient();
  const hadInProgressRef = useRef(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const searchBtnRef = useRef<HTMLButtonElement | null>(null);
  const docSearch = useSearch({ from: "/app/doc/$docId" }) as { page?: number; chunk?: number };

  const showOriginal = activeMode === "original" || activeMode === "extracted";

  // Debounce search query (200 ms)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(rawQuery), 200);
    return () => clearTimeout(timer);
  }, [rawQuery]);

  // Reset active index when query changes
  useEffect(() => {
    startTransition(() => { setActiveSearchIndex(0); });
  }, [debouncedQuery]);

  // Reset match count when search closes
  useEffect(() => {
    if (!searchOpen) { startTransition(() => { setMatchCount(0); setActiveSearchIndex(0); }); }
  }, [searchOpen]);

  const handleMatchCountChange = useCallback((n: number) => {
    setMatchCount(n);
  }, []);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    setRawQuery("");
    setDebouncedQuery("");
    setTimeout(() => searchBtnRef.current?.focus(), 0);
  }, []);

  // Focus viewer area when view mode changes
  useEffect(() => {
    viewerRef.current?.focus();
  }, [activeMode]);

  // Reset mode and image zoom when navigating to a different document.
  useEffect(() => {
    initialModeDoneRef.current = false;
    hadInProgressRef.current = false;
    startTransition(() => {
      setActiveMode("original");
      setImageZoom(null);
      setSelectedVersionId(undefined);
      closeSearch();
    });
  }, [docId, closeSearch]);

  // Poll for translation versions when there are in-progress translations.
  // When a pending/running translation completes, invalidate the preview
  // so that the next render fetches the latest translated content.
  const { data: versions } = useQuery({
    queryKey: ["doc-translation-versions", docId],
    queryFn: () => getTranslationVersions(docId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data &&
        data.some(
          (v) => v.status === "pending" || v.status === "running" || v.status === "processing",
        )
        ? 5000
        : false;
    },
  });

  // Set default mode once per document when translation versions first load.
  useEffect(() => {
    if (initialModeDoneRef.current) return;
    if (!versions) return;
    initialModeDoneRef.current = true;
    if (versions.some((v) => v.status === "available")) {
      startTransition(() => { setActiveMode("translation"); });
    }
  }, [versions]);

  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId !== undefined) return;
    if (showOriginal) return;
    if (
      versions.some(
        (v) => v.status === "pending" || v.status === "running" || v.status === "processing",
      )
    ) {
      hadInProgressRef.current = true;
      return;
    }
    if (hadInProgressRef.current) {
      hadInProgressRef.current = false;
      qc.invalidateQueries({ queryKey: ["doc-preview", docId] });
    }
  }, [versions, selectedVersionId, showOriginal, docId, qc]);

  const {
    data: preview,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["doc-preview", docId, selectedVersionId, showOriginal],
    queryFn: () =>
      measurePerformance("preview.load", () =>
        getPreview(docId, selectedVersionId, showOriginal),
      ),
    staleTime: 2 * 60_000,
  });

  // Scroll to page from search param (Phase F — citation viewer link)
  useEffect(() => {
    if (docSearch.page != null && preview) {
      const el = document.getElementById(`page-${docSearch.page}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [docSearch.page, preview]);

  const availableModes = useMemo<ViewMode[]>(() => {
    const modes: ViewMode[] = ["original"];
    if (preview?.snippet) modes.push("extracted");
    if (versions?.some((v) => v.status === "available")) modes.push("translation");
    return modes;
  }, [preview?.snippet, versions]);

  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingShell}>
          <SkeletonRow count={8} />
        </div>
      </div>
    );
  }

  if (isError || !preview) {
    return (
      <div className={styles.page}>
        <EmptyState
          title={t.document.notFoundTitle}
          body={t.document.notFoundBody}
          action={
            <Button variant="secondary" onClick={() => void refetch()}>
              {t.document.tryAgain}
            </Button>
          }
        />
      </div>
    );
  }

  // Image viewer controls are shown only when viewing an image in original mode.
  const showImageControls =
    !activeMode || activeMode === "original"
      ? preview.mime_type.startsWith("image/") && preview.mime_type !== "image/tiff"
      : false;

  const searchable = !preview.mime_type.startsWith("image/") &&
    !preview.mime_type.startsWith("audio/") &&
    !preview.mime_type.startsWith("video/");

  function handlePageKeyDown(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "f" && searchable) {
      e.preventDefault();
      setSearchOpen(true);
    }
  }

  return (
    <div className={styles.page} onKeyDown={handlePageKeyDown} tabIndex={-1}>
      <DocumentToolbar
        preview={preview}
        selectedVersionId={selectedVersionId}
        showOriginal={showOriginal}
        availableModes={availableModes}
        activeMode={activeMode}
        showImageControls={showImageControls}
        imageZoom={imageZoom}
        onVersionChange={setSelectedVersionId}
        onShowOriginalChange={(val) => setActiveMode(val ? "original" : "translation")}
        onModeChange={setActiveMode}
        onImageZoomChange={setImageZoom}
        searchable={searchable}
        searchOpen={searchOpen}
        onSearchToggle={() => setSearchOpen((o) => !o)}
        searchBtnRef={searchBtnRef}
      />
      {preview.has_newer_version && preview.latest_document_id && (
        <VersionBanner latestDocumentId={preview.latest_document_id} />
      )}
      <FidelityStatusBar
        activeMode={activeMode}
        translationQuality={preview.translation_quality}
        downloadUrl={getDownloadUrl(preview.document_id)}
      />
      {searchOpen && (
        <DocumentSearchBar
          query={rawQuery}
          matchCount={matchCount}
          activeIndex={activeSearchIndex}
          onQueryChange={setRawQuery}
          onNext={() => setActiveSearchIndex((i) => (i + 1) % Math.max(1, matchCount))}
          onPrev={() => setActiveSearchIndex((i) => (i - 1 + Math.max(1, matchCount)) % Math.max(1, matchCount))}
          onClose={closeSearch}
        />
      )}
      <div className={styles.body} ref={viewerRef} tabIndex={-1}>
        <div className={styles.previewCol}>
          <ParentContextBanner relationships={preview.relationships} />
          <RendererStatusBadge docId={docId} />
          <PreviewPane
            preview={preview}
            activeMode={activeMode}
            selectedVersionId={selectedVersionId}
            imageZoom={imageZoom}
            onImageZoomChange={setImageZoom}
            searchQuery={debouncedQuery}
            activeSearchIndex={activeSearchIndex}
            onMatchCountChange={handleMatchCountChange}
            initialPage={docSearch.page}
          />
        </div>
        <div className={styles.insightCol}>
          <InsightPane docId={docId} preview={preview} />
        </div>
      </div>
    </div>
  );
}
