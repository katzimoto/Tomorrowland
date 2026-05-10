import { api } from "./client";

export interface ExpertiseEvidence {
  doc_id: string;
  title: string;
  excerpt: string;
}

export interface ExpertiseResult {
  user_id: string;
  display_name: string;
  topics: string[];
  evidence_count: number;
  evidence: ExpertiseEvidence[];
  updated_at?: string | null;
}

export interface ExpertiseResponse {
  query: string;
  results: ExpertiseResult[];
}

export function getExpertise(query: string): Promise<ExpertiseResponse> {
  return api.get<ExpertiseResponse>(`/expertise?query=${encodeURIComponent(query)}`);
}
