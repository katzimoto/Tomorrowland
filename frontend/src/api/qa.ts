import { api } from "./client";

export interface QACitation {
  citation_id: string;
  document_id: string;
  doc_title: string;
  chunk_text: string;
  score: number;
  chunk_index: number | null;
  source_id: string | null;
  page_number?: number | null;
  section_heading?: string | null;
}

export interface QAResponse {
  question: string;
  answer: string;
  citations: QACitation[];
  model: string;
}

export function askQuestion(question: string, top_k = 5, docId?: string): Promise<QAResponse> {
  return api.post<QAResponse>("/qa", { question, top_k, ...(docId ? { document_id: docId } : {}) });
}
