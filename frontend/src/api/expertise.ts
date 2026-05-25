import { api } from "./client";

export interface ExpertiseSignals {
  views: number;
  annotations: number;
  subscriptions: number;
}

export interface ExpertiseTopDoc {
  document_id: string;
  title: string | null;
  score: number;
}

export interface ExpertiseResult {
  user_id: string;
  display_name: string | null;
  score: number;
  signals: ExpertiseSignals;
  reason: string;
  top_docs: ExpertiseTopDoc[];
}

export function getExpertise(topic: string): Promise<ExpertiseResult[]> {
  const search = new URLSearchParams({ topic });
  return api.get<ExpertiseResult[]>(`/expertise?${search.toString()}`);
}
