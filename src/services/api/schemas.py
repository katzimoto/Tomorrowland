from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    mode: str = Field(default="hybrid", max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=20, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    include_older_versions: bool = False
    sort_by: Literal["relevance", "updated_at", "created_at", "title"] = "relevance"
    sort_dir: Literal["asc", "desc"] = "desc"


class SearchResultItem(BaseModel):
    document_id: str
    source_id: str
    external_id: str | None = None
    title: str | None = None
    snippet: str | None = None
    source: str
    source_label: str
    mime_type: str
    tags: list[str] = Field(default_factory=list)
    translation_quality: str | None = None
    translation_score: float = 0.0
    score: float
    updated_at: str
    indexed_at: str
    version_number: int | None = None
    is_latest: bool | None = None
    latest_document_id: str | None = None
    has_newer_version: bool | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
    query: str = ""
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)


class PreviewResponse(BaseModel):
    document_id: str
    title: str | None = None
    mime_type: str
    translation_quality: str | None = None
    translation_score: float = 0.0
    view_count: int = 0
    metadata: dict[str, Any]
    snippet: str
    version_number: int | None = None
    is_latest: bool | None = None
    latest_document_id: str | None = None
    has_newer_version: bool | None = None
    source_language: str | None = None
    target_language: str | None = None
    status: str | None = None
    content_sha256: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    indexed_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    entities_summary: list[dict[str, Any]] | None = None
    relationships: list[DocumentRelationshipInfo] | None = None
    has_file: bool = False


class DocumentRelationshipInfo(BaseModel):
    direction: Literal["parent", "child"]
    relationship_type: str
    other_document_id: str
    title: str | None = None
    path_in_parent: str | None = None


class ConnectionTestResult(BaseModel):
    source_id: str
    status: Literal["ok", "unreachable", "auth_failed", "permission_denied", "config_invalid"]
    checked_at: str
    details: dict[str, Any] | None = None
    error: str | None = None


class CreateUserRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    is_admin: bool = False
    group_names: list[str] = Field(default_factory=list)


class CreateGroupRequest(BaseModel):
    name: str


class UpdateGroupRequest(BaseModel):
    name: str


class CreateSourceRequest(BaseModel):
    name: str
    type: Literal["folder", "nifi", "confluence", "jira", "smb"] = "folder"
    path: str | None = None
    source_language: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateSourceRequest(BaseModel):
    name: str | None = None
    source_language: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    schedule: str | None = None


class GrantPermissionRequest(BaseModel):
    group_id: str


class AdminUpdateUserGroupsRequest(BaseModel):
    group_names: list[str]


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    is_admin: bool | None = None


class AddUserToGroupRequest(BaseModel):
    user_id: str


class AddChildGroupRequest(BaseModel):
    child_group_id: str


class UpdateConfigRequest(BaseModel):
    value: Any


class DlqItem(BaseModel):
    id: str
    document_id: str | None
    error_message: str
    retry_count: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class IngestionStatusJob(BaseModel):
    id: str
    document_id: str
    source_id: str
    document_title: str | None = None
    source_name: str | None = None
    job_type: str
    status: str
    stage: str | None = None
    attempts: int = 0
    max_attempts: int = 5
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class IngestionStatusResponse(BaseModel):
    jobs: list[IngestionStatusJob]
    total: int
    summary: dict[str, int]


class DocumentTraceJob(BaseModel):
    id: str
    job_type: str
    status: str
    stage: str | None = None
    attempts: int = 0
    max_attempts: int = 5
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DocumentTraceResponse(BaseModel):
    document_id: str
    document_title: str | None = None
    source_name: str | None = None
    jobs: list[DocumentTraceJob]


# --- LDAP group search & mapping (#582) ---


class LdapGroupSearchResult(BaseModel):
    """A single LDAP group returned by a live search.  Ephemeral — never persisted."""

    display_name: str | None = None
    dn: str | None = None
    external_id: str | None = None
    external_id_attr: str | None = None
    description: str | None = None
    mail: str | None = None


class CreateLdapGroupMappingRequest(BaseModel):
    """Request body for creating an explicit LDAP group mapping."""

    ldap_dn: str = Field(..., min_length=1, max_length=1000)
    ldap_external_id_attr: str = Field(..., min_length=1, max_length=100)
    ldap_external_id: str | None = Field(default=None, max_length=256)
    ldap_display_name: str = Field(..., min_length=1, max_length=500)
    target_group_id: str = Field(..., min_length=1, max_length=36)


class LdapGroupMappingResponse(BaseModel):
    """A persisted LDAP group → Tomorrowland group mapping."""

    id: str
    ldap_dn: str
    ldap_external_id_attr: str
    ldap_external_id: str | None = None
    ldap_display_name: str
    target_group_id: str
    target_group_name: str
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
