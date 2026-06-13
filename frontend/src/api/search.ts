import { api } from "./client";

export type SearchMode = "hybrid" | "keyword" | "semantic";

export interface SearchFilters {
  source?: string[];
  file_type?: string[];
  file_extension?: string[];
  date_from?: string;
  date_to?: string;
  tags?: string[];
  language?: string;
  translation_quality?: string[];
  include_older_versions?: boolean;
  sort_by?: "relevance" | "updated_at" | "created_at" | "title";
  sort_dir?: "asc" | "desc";
}

export interface SearchResult {
  document_id: string;
  source_id: string;
  external_id: string | null;
  title: string;
  snippet: string;
  source: string;
  source_label: string;
  mime_type: string;
  tags: string[];
  translation_quality: "fast" | "high" | null;
  translation_score: number;
  score: number;
  updated_at: string;
  indexed_at: string;
  why?: Array<{ kind: string; label: string }>;
  version_number?: number;
  is_latest?: boolean;
  latest_document_id?: string;
  has_newer_version?: boolean;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  total_is_approximate?: boolean;
  candidate_count?: number;
  returned_count?: number;
  offset?: number;
  limit?: number;
  query: string;
  facets?: Record<string, Record<string, number>>;
  reranker_applied?: boolean;
  retrieval_degraded?: boolean;
}

export function search(
  query: string,
  mode: SearchMode = "hybrid",
  filters: SearchFilters = {},
  page = 1,
): Promise<SearchResponse> {
  const { include_older_versions, sort_by, sort_dir, ...backendFilters } = filters;
  return api.post<SearchResponse>("/search", {
    query,
    mode,
    filters: backendFilters,
    top_k: 100,
    page,
    page_size: 20,
    include_older_versions: include_older_versions ?? false,
    sort_by: sort_by ?? "relevance",
    sort_dir: sort_dir ?? "desc",
  });
}
