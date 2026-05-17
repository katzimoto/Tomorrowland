from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    mode: str = "hybrid"
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=20, ge=1, le=100)
    page: int = 1
    page_size: int = Field(default=20, ge=1, le=100)
    include_older_versions: bool = False


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


class CreateSourceRequest(BaseModel):
    name: str
    type: Literal["folder", "nifi", "confluence", "jira", "smb"] = "folder"
    path: str | None = None
    source_language: str | None = "en"
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateSourceRequest(BaseModel):
    name: str | None = None
    source_language: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class GrantPermissionRequest(BaseModel):
    group_id: str


class AdminUpdateUserGroupsRequest(BaseModel):
    group_names: list[str]


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
