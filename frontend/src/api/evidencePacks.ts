import { api } from "./client";

export type EvidencePackCreatedFrom = "chat" | "search" | "agent" | "manual";
export type EvidencePackItemType = "citation" | "passage" | "claim" | "note";

export interface EvidencePack {
  id: string;
  owner_user_id: string;
  title: string;
  description: string | null;
  source_scope: Record<string, unknown> | null;
  created_from: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EvidencePackItem {
  id: string;
  evidence_pack_id: string;
  document_id: string;
  item_type: string;
  text_excerpt: string;
  chunk_id: string | null;
  citation_id: string | null;
  page_number: number | null;
  section_heading: string | null;
  translated_text: string | null;
  claim: string | null;
  created_at: string;
}

export interface EvidencePackDetail extends EvidencePack {
  items: EvidencePackItem[];
}

export interface CreateEvidencePackRequest {
  title: string;
  description?: string | null;
  created_from?: EvidencePackCreatedFrom;
}

/** Fields accepted by `POST /evidence-packs/{id}/items`. */
export interface EvidencePackItemInput {
  document_id: string;
  item_type: EvidencePackItemType;
  text_excerpt: string;
  chunk_id?: string | null;
  citation_id?: string | null;
  page_number?: number | null;
  section_heading?: string | null;
  translated_text?: string | null;
  claim?: string | null;
}

export function listEvidencePacks(): Promise<{ items: EvidencePack[] }> {
  return api.get<{ items: EvidencePack[] }>("/evidence-packs");
}

export function getEvidencePack(packId: string): Promise<EvidencePackDetail> {
  return api.get<EvidencePackDetail>(`/evidence-packs/${packId}`);
}

export function createEvidencePack(req: CreateEvidencePackRequest): Promise<EvidencePack> {
  return api.post<EvidencePack>("/evidence-packs", req);
}

export interface UpdateEvidencePackRequest {
  title?: string;
  description?: string | null;
}

export function updateEvidencePack(
  packId: string,
  req: UpdateEvidencePackRequest,
): Promise<EvidencePack> {
  return api.patch<EvidencePack>(`/evidence-packs/${packId}`, req);
}

export function deleteEvidencePack(packId: string): Promise<void> {
  return api.delete<void>(`/evidence-packs/${packId}`);
}

export function removeEvidencePackItem(packId: string, itemId: string): Promise<void> {
  return api.delete<void>(`/evidence-packs/${packId}/items/${itemId}`);
}

export function addEvidencePackItem(
  packId: string,
  item: EvidencePackItemInput,
): Promise<EvidencePackItem> {
  return api.post<EvidencePackItem>(`/evidence-packs/${packId}/items`, item);
}
