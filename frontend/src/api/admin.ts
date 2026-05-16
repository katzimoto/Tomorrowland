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
  created_at: string | null;
  last_sync_status: "success" | "failed" | null;
  last_sync_indexed: number | null;
  last_sync_skipped: number | null;
  last_sync_failed: number | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
  last_validation_status: "ok" | "unreachable" | "auth_failed" | "permission_denied" | "config_invalid" | null;
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
  status: "ok" | "unreachable" | "auth_failed" | "permission_denied" | "config_invalid";
  checked_at: string;
  details?: Record<string, unknown>;
  error?: string;
}

export interface SourceGroup {
  id: string;
  name: string;
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
    api.post<SourceTestResult>(`/admin/sources/${sourceId}/test-connection`, {}),
  getSource: (sourceId: string) =>
    api.get<SourceDetail>(`/admin/sources/${sourceId}`),
  listGroups: () => api.get<{ id: string; name: string }[]>("/admin/groups"),
  grantPermission: (sourceId: string, groupId: string) =>
    api.post(`/admin/sources/${sourceId}/permissions`, { group_id: groupId }),
  revokePermission: (sourceId: string, groupId: string) =>
    api.delete(`/admin/sources/${sourceId}/permissions/${groupId}`),
  updateSource: (sourceId: string, payload: Record<string, unknown>) =>
    api.put(`/admin/sources/${sourceId}`, payload),
  listUsers: () => api.get<UserDetail[]>("/admin/users"),
  getUser: (userId: string) => api.get<UserDetail>(`/admin/users/${userId}`),
  setUserGroups: (userId: string, groupNames: string[]) =>
    api.put(`/admin/users/${userId}/groups`, { group_names: groupNames }),
  listGroupUsers: (groupId: string) =>
    api.get<GroupMember[]>(`/admin/groups/${groupId}/users`),
  addUserToGroup: (groupId: string, userId: string) =>
    api.post(`/admin/groups/${groupId}/users`, { user_id: userId }),
  removeUserFromGroup: (groupId: string, userId: string) =>
    api.delete(`/admin/groups/${groupId}/users/${userId}`),
  listGroupChildren: (groupId: string) =>
    api.get<ChildGroup[]>(`/admin/groups/${groupId}/children`),
  addChildGroup: (groupId: string, childGroupId: string) =>
    api.post(`/admin/groups/${groupId}/children`, { child_group_id: childGroupId }),
  removeChildGroup: (groupId: string, childGroupId: string) =>
    api.delete(`/admin/groups/${groupId}/children/${childGroupId}`),
};

export interface UserDetail {
  id: string;
  email: string;
  display_name: string | null;
  auth_source: string;
  is_admin: boolean;
  created_at: string | null;
  groups: SourceGroup[];
}
