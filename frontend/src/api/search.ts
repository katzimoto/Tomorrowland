import { api } from "./client";

export type SearchMode = "hybrid" | "keyword" | "semantic";

export interface SearchFilters {
  source?: string[];
  file_type?: string[];
  date_from?: string;
  date_to?: string;
  tags?: string[];
  language?: string;
  translation_quality?: string[];
}

export interface SearchResult {
  doc_id: string;
  source_id: string;
  external_id: string | null;
  title: string;
  snippet: string;
  source: string;
  source_label: string;
  mime_type: string;
  tags: string[];
  translation_quality: "fast" | "high" | null;
  score: number;
  updated_at: string;
  indexed_at: string;
  why?: Array<{ kind: string; label: string }>;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}

export function search(
  query: string,
  mode: SearchMode = "hybrid",
  filters: SearchFilters = {},
  top_k = 20,
): Promise<SearchResponse> {
  return api.post<SearchResponse>("/search", { query, mode, filters, top_k });
}
