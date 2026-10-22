"""Public Day 17 contracts. Internal storage paths and checkpoints stay private."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hybrid_rag_search.models.content import (
    CollectionPermission,
    DocumentStatus,
    IngestionJobStatus,
    IngestionStage,
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)


class CollectionCreate(Contract):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=2000)


class CollectionEdit(Contract):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CollectionView(CollectionCreate):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime


class GrantSet(Contract):
    permission: CollectionPermission


class GrantView(GrantSet):
    membership_id: UUID


class MemberView(Contract):
    membership_id: UUID
    user_id: UUID
    display_name: str
    role: Literal["owner", "admin", "member"]


class DocumentView(Contract):
    id: UUID
    collection_id: UUID
    original_filename: str
    media_type: str
    size_bytes: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class JobView(Contract):
    id: UUID
    document_id: UUID
    status: IngestionJobStatus
    stage: IngestionStage
    attempts: int
    max_attempts: int
    error_code: str | None
    failure_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_attempt_at: datetime | None


class UploadView(Contract):
    document_id: UUID
    job_id: UUID
    duplicate: bool
    dispatch: Literal["sent", "pending", "not_needed"]


class ErrorDetail(Contract):
    code: str
    message: str
    request_id: str


class ErrorView(Contract):
    error: ErrorDetail


class CollectionCapabilities(Contract):
    can_upload: bool
    can_manage: bool
