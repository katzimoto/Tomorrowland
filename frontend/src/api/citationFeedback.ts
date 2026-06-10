import { api } from "./client";

export type CitationFeedbackType =
  | "correct"
  | "wrong_passage"
  | "right_document_wrong_location"
  | "missing_better_source"
  | "unsupported_claim"
  | "permission_concern"
  | "other";

export interface CitationFeedbackRequest {
  citation_id?: string | null;
  message_id?: string | null;
  document_id: string;
  chunk_id?: string | null;
  feedback_type: CitationFeedbackType;
  comment?: string | null;
}

export function submitCitationFeedback(
  req: CitationFeedbackRequest,
): Promise<{ id: string; ok: boolean }> {
  return api.post<{ id: string; ok: boolean }>("/citation-feedback", req);
}
