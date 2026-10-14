"""Workspace-scoped management endpoints for the thin frontend."""

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from hybrid_rag_search.api import DemoUser, Policy
from hybrid_rag_search.api_errors import APIError
from hybrid_rag_search.authorization import AccessDenied
from hybrid_rag_search.config import get_settings
from hybrid_rag_search.documents import DocumentNotFound, DocumentUnavailable
from hybrid_rag_search.ingestion.dispatch import DramatiqJobPublisher
from hybrid_rag_search.ingestion.indexing import IndexWriteError
from hybrid_rag_search.management import ManagementService
from hybrid_rag_search.management_schemas import (
    CollectionCreate,
    CollectionEdit,
    CollectionView,
    DocumentView,
    ErrorView,
    GrantSet,
    GrantView,
    JobView,
    MemberView,
    UploadView,
)
from hybrid_rag_search.models import Collection, CollectionGrant, Document, Membership, User

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}",
    tags=["management"],
    responses={code: {"model": ErrorView} for code in (401, 403, 404, 409, 413, 415, 422, 503)},
)
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
UploadKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$"),
]


def management(policy: Policy) -> ManagementService:
    from hybrid_rag_search.worker import ingest_document

    return ManagementService(policy.sessions, get_settings(), DramatiqJobPublisher(ingest_document))


Service = Annotated[ManagementService, Depends(management)]


@router.get("/collections", response_model=list[CollectionView])
async def collections(
    workspace_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[Collection]:
    scope = await policy.scope(demo_user, workspace_id)
    async with service.sessions() as session:
        return list(
            await session.scalars(
                select(Collection)
                .where(
                    Collection.tenant_id == workspace_id, Collection.id.in_(scope.collection_ids)
                )
                .order_by(Collection.name, Collection.id)
                .limit(limit)
                .offset(offset)
            )
        )


@router.post("/collections", response_model=CollectionView, status_code=201)
async def create_collection(
    workspace_id: UUID,
    body: CollectionCreate,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Collection:
    member = await policy.require(demo_user, workspace_id, "manage")
    try:
        async with service.sessions.begin() as session:
            row = Collection(tenant_id=workspace_id, **body.model_dump())
            session.add(row)
            await session.flush()
            service.audit(session, member, "collection.created", "collection", row.id)
        return row
    except IntegrityError:
        raise APIError(409, "collection_conflict", "Collection slug already exists.") from None


@router.get("/collections/{collection_id}", response_model=CollectionView)
async def collection(
    workspace_id: UUID,
    collection_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Collection:
    await policy.scope(demo_user, workspace_id, collection_id)
    return await service.collection(workspace_id, collection_id)


@router.patch("/collections/{collection_id}", response_model=CollectionView)
async def edit_collection(
    workspace_id: UUID,
    collection_id: UUID,
    body: CollectionEdit,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Collection:
    member = await policy.require(demo_user, workspace_id, "manage", collection_id)
    async with service.sessions.begin() as session:
        row = await session.scalar(
            select(Collection)
            .where(Collection.tenant_id == workspace_id, Collection.id == collection_id)
            .with_for_update()
        )
        if row is None:
            raise APIError(404, "not_found", "Collection not found.")
        row.name, row.description = body.name, body.description
        await session.flush()
        service.audit(session, member, "collection.updated", "collection", row.id)
        await session.refresh(row)
    return row


@router.get("/members", response_model=list[MemberView])
async def members(
    workspace_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
    limit: Limit = 50,
    offset: Offset = 0,
    collection_id: UUID | None = None,
) -> list[MemberView]:
    # Collection managers need the same-workspace picker; other members do not.
    await policy.require(demo_user, workspace_id, "manage", collection_id)
    async with service.sessions() as session:
        rows = await session.execute(
            select(Membership, User.display_name)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == workspace_id)
            .order_by(User.display_name, Membership.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            MemberView(
                membership_id=m.id,
                user_id=m.user_id,
                display_name=name,
                role=cast(Literal["owner", "admin", "member"], m.role),
            )
            for m, name in rows
        ]


@router.get("/collections/{collection_id}/grants", response_model=list[GrantView])
async def grants(
    workspace_id: UUID,
    collection_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[CollectionGrant]:
    await policy.require(demo_user, workspace_id, "manage", collection_id)
    async with service.sessions() as session:
        return list(
            await session.scalars(
                select(CollectionGrant)
                .where(
                    CollectionGrant.tenant_id == workspace_id,
                    CollectionGrant.collection_id == collection_id,
                )
                .order_by(CollectionGrant.membership_id)
                .limit(limit)
                .offset(offset)
            )
        )


@router.put("/collections/{collection_id}/grants/{membership_id}", status_code=204)
async def set_grant(
    workspace_id: UUID,
    collection_id: UUID,
    membership_id: UUID,
    body: GrantSet,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Response:
    member = await policy.require(demo_user, workspace_id, "manage", collection_id)
    await service.set_grant(member, collection_id, membership_id, body.permission)
    return Response(status_code=204)


@router.delete("/collections/{collection_id}/grants/{membership_id}", status_code=204)
async def revoke_grant(
    workspace_id: UUID,
    collection_id: UUID,
    membership_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Response:
    member = await policy.require(demo_user, workspace_id, "manage", collection_id)
    await service.set_grant(member, collection_id, membership_id, None)
    return Response(status_code=204)


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentView])
async def documents(
    workspace_id: UUID,
    collection_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[Document]:
    await policy.scope(demo_user, workspace_id, collection_id)
    async with service.sessions() as session:
        return list(
            await session.scalars(
                select(Document)
                .where(
                    Document.tenant_id == workspace_id,
                    Document.collection_id == collection_id,
                    Document.status != "deleted",
                )
                .order_by(Document.created_at, Document.id)
                .limit(limit)
                .offset(offset)
            )
        )


@router.post("/collections/{collection_id}/documents", response_model=UploadView, status_code=202)
async def upload_document(
    workspace_id: UUID,
    collection_id: UUID,
    file: UploadFile,
    idempotency_key: UploadKey,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> UploadView:
    try:
        member = await policy.require(demo_user, workspace_id, "write", collection_id)
        content = await file.read(service.settings.upload_max_bytes + 1)
        if len(content) > service.settings.upload_max_bytes:
            raise APIError(413, "upload_too_large", "File exceeds the configured upload limit.")
        if not file.filename or not file.filename.strip() or len(file.filename) > 255:
            raise APIError(
                422, "invalid_filename", "A filename of at most 255 characters is required."
            )
        media_type = (file.content_type or "").partition(";")[0].strip().lower()
        if media_type not in {
            "text/plain",
            "text/markdown",
            "text/x-markdown",
            "text/html",
            "application/xhtml+xml",
            "application/pdf",
        }:
            raise APIError(
                415, "unsupported_media_type", "Use a supported PDF, text, Markdown, or HTML file."
            )
        return await service.upload(
            member, collection_id, idempotency_key, file.filename, media_type, content
        )
    except DocumentUnavailable:
        raise APIError(
            409, "document_unavailable", "Document is being deleted; retry the upload."
        ) from None
    except OSError:
        raise APIError(503, "storage_unavailable", "Upload could not be saved.") from None
    finally:
        await file.close()


async def accessible_document(
    policy: Policy,
    service: ManagementService,
    demo_user: UUID | None,
    workspace_id: UUID,
    document_id: UUID,
) -> Document:
    # Metadata/job history remains inspectable after deletion; content does not.
    try:
        row = await service.document(workspace_id, document_id)
        await policy.scope(demo_user, workspace_id, row.collection_id)
    except APIError:
        await policy.user(demo_user)
        raise
    except AccessDenied as error:
        if error.status_code != 401:
            raise APIError(404, "not_found", "Document not found.") from None
        raise
    return row


@router.get("/documents/{document_id}", response_model=DocumentView)
async def document(
    workspace_id: UUID,
    document_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Document:
    return await accessible_document(policy, service, demo_user, workspace_id, document_id)


@router.get("/jobs/{job_id}", response_model=JobView)
async def job(
    workspace_id: UUID, job_id: UUID, policy: Policy, service: Service, demo_user: DemoUser = None
) -> JobView:
    await policy.user(demo_user)
    row = await service.job(workspace_id, job_id)
    await accessible_document(policy, service, demo_user, workspace_id, row.document_id)
    return row


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    policy: Policy,
    service: Service,
    demo_user: DemoUser = None,
) -> Response:
    row = await accessible_document(policy, service, demo_user, workspace_id, document_id)
    member = await policy.require(demo_user, workspace_id, "write", row.collection_id)
    try:
        await service.delete_document(member, document_id)
    except DocumentNotFound:
        raise APIError(404, "not_found", "Document not found.") from None
    except (OSError, ValueError, IndexWriteError):
        raise APIError(
            503, "deletion_pending", "Cleanup failed; retry this delete request."
        ) from None
    return Response(status_code=204)
