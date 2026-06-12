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
  supported_versions?: Record<string, { value: string; label: string }[]>;
}

export interface Source {
  id: string;
  name: string;
  type: string;
  path: string | null;
  source_language: string | null;
  enabled: boolean;
  schedule: string | null;
  created_at: string | null;
  last_sync_status: "success" | "failed" | null;
  last_sync_indexed: number | null;
  last_sync_skipped: number | null;
  last_sync_failed: number | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
  last_validation_status:
    | "ok"
    | "unreachable"
    | "auth_failed"
    | "permission_denied"
    | "config_invalid"
    | null;
  last_validation_error: string | null;
  last_validated_at: string | null;
}

export interface CreateSourcePayload {
  name: string;
  type: string;
  path?: string | null;
  source_language: string | null;
  enabled: boolean;
  config: Record<string, string>;
}

export interface SyncResult {
  status: "success" | "partial_failure" | "failed";
  discovered: number;
  created: number;
  skipped: number;
  enqueued: number;
  failed_discovery: number;
  failed_enqueue: number;
}

export interface SourceTestResult {
  source_id: string;
  status:
    | "ok"
    | "unreachable"
    | "auth_failed"
    | "permission_denied"
    | "config_invalid";
  checked_at: string;
  details?: Record<string, unknown>;
  error?: string;
}

export interface SourceGroup {
  id: string;
  name: string;
}

export interface PipelineJob {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  max_attempts: number;
  stage: string | null;
  last_error: string | null;
  rabbit_message_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SourceDocument {
  id: string;
  title: string | null;
  external_id: string;
  status: string;
  mime_type: string;
  source_language: string | null;
  translation_quality: string | null;
  created_at: string | null;
  total_jobs: number;
  succeeded_jobs: number;
  pending_jobs: number;
  failed_jobs: number;
  jobs: PipelineJob[];
  // Parser strategy metadata (#670)
  parser_name: string | null;
  fallback_chain: string[] | null;
  extraction_status: string | null;
  extraction_confidence: number | null;
  extraction_duration_ms: number | null;
  char_count: number | null;
  chunk_count: number | null;
  ocr_needed: boolean;
  ocr_performed: boolean | null;
  translation_status: string | null;
  layout_blocks_available: boolean;
  table_block_count: number;
  figure_block_count: number;
  last_error: string | null;
}

export interface SourceDocumentsResponse {
  documents: SourceDocument[];
  total: number;
  parser_summary?: ParserSummary;
}

export interface ParserSummary {
  documents_by_parser: Record<string, number>;
  total_extracted: number;
  total_ocr_done: number;
  total_failed: number;
  total_documents: number;
  avg_char_count: number;
}

export interface SourceDetail extends Source {
  config: Record<string, unknown>;
  groups: SourceGroup[];
}

export interface GroupMember {
  id: string;
  email: string;
  display_name: string | null;
}

export interface ChildGroup {
  id: string;
  name: string;
}

export const adminApi = {
  connectorTypes: () => api.get<ConnectorType[]>("/admin/connector-types"),
  sourceLanguages: () => api.get<string[]>("/admin/source-languages"),
  listSources: () => api.get<Source[]>("/admin/sources"),
  createSource: (payload: CreateSourcePayload) =>
    api.post<Source>("/admin/sources", payload),
  syncSource: (sourceId: string) =>
    api.post<SyncResult>(`/admin/ingestion/${sourceId}/sync-now`, {}),
  testSource: (sourceId: string) =>
    api.post<SourceTestResult>(
      `/admin/sources/${sourceId}/test-connection`,
      {},
    ),
  getSource: (sourceId: string) =>
    api.get<SourceDetail>(`/admin/sources/${sourceId}`),
  getSourceDocuments: (sourceId: string, limit = 50, offset = 0) =>
    api.get<SourceDocumentsResponse>(
      `/admin/sources/${sourceId}/documents?limit=${limit}&offset=${offset}`,
    ),
  requeueDocument: (documentId: string) =>
    api.post<{ requeued: number }>(
      `/admin/documents/${documentId}/requeue`,
      {},
    ),
  deleteDocument: (documentId: string) =>
    api.delete(`/admin/documents/${documentId}`),
  deleteSource: (sourceId: string) => api.delete(`/admin/sources/${sourceId}`),
  listGroups: () => api.get<{ id: string; name: string }[]>("/admin/groups"),
  grantPermission: (sourceId: string, groupId: string) =>
    api.post(`/admin/sources/${sourceId}/permissions`, { group_id: groupId }),
  revokePermission: (sourceId: string, groupId: string) =>
    api.delete(`/admin/sources/${sourceId}/permissions/${groupId}`),
  updateSource: (sourceId: string, payload: Record<string, unknown>) =>
    api.put(`/admin/sources/${sourceId}`, payload),
  listUsers: () => api.get<UserDetail[]>("/admin/users"),
  getUser: (userId: string) => api.get<UserDetail>(`/admin/users/${userId}`),
  updateUser: (
    userId: string,
    payload: { display_name?: string | null; is_admin?: boolean | null },
  ) => api.patch<UserDetail>(`/admin/users/${userId}`, payload),
  setUserGroups: (userId: string, groupNames: string[]) =>
    api.put(`/admin/users/${userId}/groups`, { group_names: groupNames }),
  createGroup: (name: string) =>
    api.post<{ id: string; name: string }>("/admin/groups", { name }),
  deleteGroup: (groupId: string) => api.delete(`/admin/groups/${groupId}`),
  renameGroup: (groupId: string, name: string) =>
    api.put<{ id: string; name: string }>(`/admin/groups/${groupId}`, { name }),
  listGroupUsers: (groupId: string) =>
    api.get<GroupMember[]>(`/admin/groups/${groupId}/users`),
  addUserToGroup: (groupId: string, userId: string) =>
    api.post(`/admin/groups/${groupId}/users`, { user_id: userId }),
  removeUserFromGroup: (groupId: string, userId: string) =>
    api.delete(`/admin/groups/${groupId}/users/${userId}`),
  listGroupChildren: (groupId: string) =>
    api.get<ChildGroup[]>(`/admin/groups/${groupId}/children`),
  addChildGroup: (groupId: string, childGroupId: string) =>
    api.post(`/admin/groups/${groupId}/children`, {
      child_group_id: childGroupId,
    }),
  removeChildGroup: (groupId: string, childGroupId: string) =>
    api.delete(`/admin/groups/${groupId}/children/${childGroupId}`),

  // --- Ingestion pipeline status ---
  getIngestionStatus: (params: {
    status?: string;
    source_id?: string;
    since?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.source_id) qs.set("source_id", params.source_id);
    if (params.since) qs.set("since", params.since);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return api.get<IngestionStatusResponse>(
      `/admin/ingestion/status${q ? `?${q}` : ""}`,
    );
  },

  getDocumentTrace: (documentId: string) =>
    api.get<DocumentTraceResponse>(`/admin/ingestion/status/${documentId}`),

  // --- Model Providers ---
  listModelProviders: () => api.get<ModelProvider[]>("/admin/model-providers"),
  createModelProvider: (payload: ModelProviderCreatePayload) =>
    api.post<ModelProvider>("/admin/model-providers", payload),
  getModelProvider: (providerId: string) =>
    api.get<ModelProvider>(`/admin/model-providers/${providerId}`),
  updateModelProvider: (
    providerId: string,
    payload: ModelProviderUpdatePayload,
  ) => api.put<ModelProvider>(`/admin/model-providers/${providerId}`, payload),
  deleteModelProvider: (providerId: string) =>
    api.delete(`/admin/model-providers/${providerId}`),
  testModelProvider: (providerId: string) =>
    api.post<ProviderTestResult>(
      `/admin/model-providers/${providerId}/test`,
      {},
    ),
  discoverModels: (providerId: string) =>
    api.post<ProviderDiscoverResult[]>(
      `/admin/model-providers/${providerId}/discover`,
      {},
    ),
  reloadModelProviders: () =>
    api.post<{ status: string }>("/admin/model-providers/reload", {}),

  // --- Model Descriptors ---
  listModelDescriptors: (providerId: string) =>
    api.get<ModelDescriptor[]>(
      `/admin/model-providers/${providerId}/descriptors`,
    ),
  createModelDescriptor: (
    providerId: string,
    payload: ModelDescriptorCreatePayload,
  ) =>
    api.post<ModelDescriptor>(
      `/admin/model-providers/${providerId}/descriptors`,
      payload,
    ),
  updateModelDescriptor: (
    descriptorId: string,
    payload: Partial<ModelDescriptorCreatePayload>,
  ) =>
    api.put<ModelDescriptor>(
      `/admin/model-descriptors/${descriptorId}`,
      payload,
    ),
  deleteModelDescriptor: (descriptorId: string) =>
    api.delete(`/admin/model-descriptors/${descriptorId}`),

  // --- Task Defaults ---
  listTaskDefaults: () =>
    api.get<ModelTaskDefault[]>("/admin/model-task-defaults"),
  getTaskDefault: (taskType: string) =>
    api.get<ModelTaskDefault>(`/admin/model-task-defaults/${taskType}`),
  setTaskDefault: (taskType: string, payload: ModelTaskDefaultSetPayload) =>
    api.put<ModelTaskDefault>(
      `/admin/model-task-defaults/${taskType}`,
      payload,
    ),
  deleteTaskDefault: (taskType: string) =>
    api.delete(`/admin/model-task-defaults/${taskType}`),

  // --- LDAP Group Search & Mappings ---
  searchLdapGroups: (query: string, limit?: number) => {
    const qs = new URLSearchParams({ q: query });
    if (limit !== undefined) qs.set("limit", String(limit));
    return api.get<LdapGroupSearchResult[]>(
      `/admin/ldap/groups/search?${qs.toString()}`,
    );
  },
  listLdapGroupMappings: () =>
    api.get<LdapGroupMapping[]>("/admin/ldap/group-mappings"),
  createLdapGroupMapping: (payload: LdapGroupMappingCreatePayload) =>
    api.post<LdapGroupMapping>("/admin/ldap/group-mappings", payload),
  deleteLdapGroupMapping: (mappingId: string) =>
    api.delete(`/admin/ldap/group-mappings/${mappingId}`),
};

export interface IngestionStatusJob {
  id: string;
  document_id: string;
  source_id: string;
  document_title: string | null;
  source_name: string | null;
  job_type: string;
  status: string;
  stage: string | null;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface IngestionStatusResponse {
  jobs: IngestionStatusJob[];
  total: number;
  summary: Record<string, number>;
}

export interface DocumentTraceJob {
  id: string;
  job_type: string;
  status: string;
  stage: string | null;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentTraceResponse {
  document_id: string;
  document_title: string | null;
  source_name: string | null;
  jobs: DocumentTraceJob[];
}

export interface UserDetail {
  id: string;
  email: string;
  display_name: string | null;
  auth_source: string;
  is_admin: boolean;
  created_at: string | null;
  groups: SourceGroup[];
}

// --- Model Providers ---

export interface ModelProvider {
  id: string;
  name: string;
  provider_type: string;
  description: string | null;
  base_url: string | null;
  credential_set: boolean;
  locality: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelProviderCreatePayload {
  name: string;
  provider_type: string;
  description?: string | null;
  base_url?: string | null;
  credential_value?: string | null;
  locality?: string;
  enabled?: boolean;
}

export interface ModelProviderUpdatePayload {
  name?: string;
  provider_type?: string;
  description?: string | null;
  base_url?: string | null;
  credential_value?: string | null;
  locality?: string;
  enabled?: boolean;
}

export interface ModelDescriptor {
  id: string;
  provider_id: string;
  model_name: string;
  display_name: string | null;
  description: string | null;
  capabilities: Record<string, unknown> | null;
  context_window: number | null;
  max_output_tokens: number | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelDescriptorCreatePayload {
  model_name: string;
  display_name?: string | null;
  description?: string | null;
  capabilities?: Record<string, unknown> | null;
  context_window?: number | null;
  max_output_tokens?: number | null;
  enabled?: boolean;
}

export interface ModelTaskDefault {
  task_type: string;
  provider_id: string;
  model_descriptor_id: string | null;
  parameters: Record<string, unknown> | null;
  updated_at: string;
}

export interface ModelTaskDefaultSetPayload {
  provider_id: string;
  model_descriptor_id?: string | null;
  parameters?: Record<string, unknown> | null;
}

export interface ProviderTestResult {
  healthy: boolean;
  latency_ms: number | null;
  error: string | null;
  provider_type: string;
}

export interface ProviderDiscoverResult {
  model_name: string;
  display_name?: string | null;
}

// --- LDAP Group Search & Mappings ---

export interface LdapGroupSearchResult {
  dn: string;
  display_name: string;
  external_id: string | null;
  description: string | null;
  mail: string | null;
}

export interface LdapGroupMapping {
  id: string;
  ldap_dn: string;
  ldap_external_id_attr: string;
  ldap_external_id: string | null;
  ldap_display_name: string;
  target_group_id: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LdapGroupMappingCreatePayload {
  ldap_dn: string;
  ldap_external_id_attr: string;
  ldap_external_id: string | null;
  ldap_display_name: string;
  target_group_id: string;
}
