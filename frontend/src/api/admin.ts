import { api } from "./client";

export interface ConnectorField {
  key: string;
  label: string;
  required: boolean;
  sensitive: boolean;
  placeholder: string;
}

export interface ConnectorType {
  type: string;
  label: string;
  fields: ConnectorField[];
}

export interface Source {
  id: string;
  name: string;
  type: string;
  path: string | null;
  source_language: string | null;
  enabled: boolean;
  created_at: string | null;
  last_sync_status: "success" | "failed" | null;
  last_sync_indexed: number | null;
  last_sync_skipped: number | null;
  last_sync_failed: number | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
}

export interface CreateSourcePayload {
  name: string;
  type: string;
  path?: string | null;
  source_language: string;
  enabled: boolean;
  config: Record<string, string>;
}

export interface SyncResult {
  status: "success" | "failed";
  indexed: number;
  skipped: number;
  failed: number;
}

export interface SourceTestResult {
  status: "ok";
  message: string;
}

export const adminApi = {
  connectorTypes: () => api.get<ConnectorType[]>("/admin/connector-types"),
  listSources: () => api.get<Source[]>("/admin/sources"),
  createSource: (payload: CreateSourcePayload) =>
    api.post<Source>("/admin/sources", payload),
  syncSource: (sourceId: string) =>
    api.post<SyncResult>(`/admin/ingestion/${sourceId}/sync-now`, {}),
  testSource: (sourceId: string) =>
    api.post<SourceTestResult>(`/admin/sources/${sourceId}/test-connection`, {}),
};
