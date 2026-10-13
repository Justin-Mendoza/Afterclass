"""Management operations reuse durable ingestion and local storage boundaries."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hybrid_rag_search.api_errors import APIError
from hybrid_rag_search.config import Settings
from hybrid_rag_search.documents import DocumentService
from hybrid_rag_search.ingestion.artifacts import LocalArtifactStorage
from hybrid_rag_search.ingestion.dispatch import JobPublisher
from hybrid_rag_search.ingestion.jobs import IngestionJobService
from hybrid_rag_search.ingestion.runtime import configured_pipeline_version
from hybrid_rag_search.management_schemas import JobView, UploadView
from hybrid_rag_search.models import (
    AuditEvent,
    Collection,
    CollectionGrant,
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
    IngestionStage,
    Membership,
    UploadReceipt,
)
from hybrid_rag_search.opensearch_index import OpenSearchDocumentIndex
from hybrid_rag_search.storage import LocalFileStorage, storage_key


class ManagementService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        publisher: JobPublisher,
    ) -> None:
        self.sessions, self.settings, self.publisher = sessions, settings, publisher
        self.originals = DocumentService(sessions, LocalFileStorage(settings.storage_root))
        self.jobs = IngestionJobService(sessions, publisher)
        self.index = OpenSearchDocumentIndex(
            settings.opensearch_url,
            settings.opensearch_write_alias,
            settings.cohere_embed_dimensions,
        )

    @staticmethod
    def audit(
        session: AsyncSession, member: Membership, action: str, entity_type: str, entity_id: UUID
    ) -> None:
        session.add(
            AuditEvent(
                tenant_id=member.tenant_id,
                actor_membership_id=member.id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
            )
        )

    async def collection(self, tenant: UUID, collection: UUID) -> Collection:
        async with self.sessions() as session:
            row = await session.scalar(
                select(Collection).where(
                    Collection.tenant_id == tenant, Collection.id == collection
                )
            )
        if row is None:
            raise APIError(404, "not_found", "Collection not found.")
        return row

    async def set_grant(
        self, member: Membership, collection: UUID, target: UUID, permission: str | None
    ) -> None:
        async with self.sessions.begin() as session:
            # Serialize grant changes and verify both IDs within the workspace.
            row = await session.scalar(
                select(Collection)
                .where(Collection.tenant_id == member.tenant_id, Collection.id == collection)
                .with_for_update()
            )
            membership = await session.scalar(
                select(Membership).where(
                    Membership.tenant_id == member.tenant_id, Membership.id == target
                )
            )
            if row is None or membership is None:
                raise APIError(404, "not_found", "Collection or member not found.")
            grant = await session.scalar(
                select(CollectionGrant).where(
                    CollectionGrant.tenant_id == member.tenant_id,
                    CollectionGrant.collection_id == collection,
                    CollectionGrant.membership_id == target,
                )
            )
            if permission is None:
                await session.execute(
                    delete(CollectionGrant).where(
                        CollectionGrant.tenant_id == member.tenant_id,
                        CollectionGrant.collection_id == collection,
                        CollectionGrant.membership_id == target,
                    )
                )
            elif grant is not None:
                grant.permission = permission
            else:
                session.add(
                    CollectionGrant(
                        tenant_id=member.tenant_id,
                        collection_id=collection,
                        membership_id=target,
                        permission=permission,
                    )
                )
            self.audit(session, member, "collection.permissions", "collection", collection)

    async def upload(
        self,
        member: Membership,
        collection: UUID,
        key: str,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> UploadView:
        fingerprint = hashlib.sha256(
            json.dumps(
                [filename, media_type, hashlib.sha256(content).hexdigest()],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(Collection)
                .where(Collection.tenant_id == member.tenant_id, Collection.id == collection)
                .with_for_update()
            )
            if row is None:
                raise APIError(404, "not_found", "Collection not found.")
            receipt = await session.scalar(
                select(UploadReceipt).where(
                    UploadReceipt.tenant_id == member.tenant_id,
                    UploadReceipt.collection_id == collection,
                    UploadReceipt.membership_id == member.id,
                    UploadReceipt.key == key,
                )
            )
            if receipt is not None:
                if receipt.fingerprint != fingerprint:
                    raise APIError(
                        409, "idempotency_conflict", "Upload key was used for a different request."
                    )
                document = await session.get(Document, receipt.document_id)
                if document is None or document.status in (
                    DocumentStatus.DELETING,
                    DocumentStatus.DELETED,
                ):
                    raise APIError(
                        409, "upload_deleted", "This upload was deleted; use a new upload key."
                    )
                job = await session.get(IngestionJob, receipt.job_id)
                assert job is not None
                status = IngestionJobStatus(job.status)
            else:
                uploaded = await self.originals.upload_in_session(
                    session, member.tenant_id, collection, filename, media_type, content
                )
                queued = await self.jobs.enqueue_in_session(
                    session,
                    member.tenant_id,
                    uploaded.document_id,
                    configured_pipeline_version(self.settings),
                )
                receipt = UploadReceipt(
                    tenant_id=member.tenant_id,
                    collection_id=collection,
                    membership_id=member.id,
                    key=key,
                    fingerprint=fingerprint,
                    document_id=uploaded.document_id,
                    job_id=queued.job_id,
                    duplicate=uploaded.duplicate,
                )
                session.add(receipt)
                self.audit(session, member, "document.upload", "document", uploaded.document_id)
                status = queued.status
        dispatch: Literal["sent", "pending", "not_needed"] = "not_needed"
        if status is IngestionJobStatus.QUEUED:
            try:
                await self.publisher.publish(receipt.job_id)
                dispatch = "sent"
            except Exception:
                # Durable state is committed. Redis only owns delivery, not acceptance.
                dispatch = "pending"
        return UploadView(
            document_id=receipt.document_id,
            job_id=receipt.job_id,
            duplicate=receipt.duplicate,
            dispatch=dispatch,
        )

    async def document(self, tenant: UUID, document: UUID) -> Document:
        async with self.sessions() as session:
            row = await session.scalar(
                select(Document).where(Document.tenant_id == tenant, Document.id == document)
            )
        if row is None:
            raise APIError(404, "not_found", "Document not found.")
        return row

    async def job(self, tenant: UUID, job_id: UUID) -> JobView:
        async with self.sessions() as session:
            job = await session.scalar(
                select(IngestionJob).where(
                    IngestionJob.tenant_id == tenant, IngestionJob.id == job_id
                )
            )
        if job is None:
            raise APIError(404, "not_found", "Job not found.")
        # Raw provider/storage exception text can contain content, paths, or secrets.
        return JobView(
            id=job.id,
            document_id=job.document_id,
            status=IngestionJobStatus(job.status),
            stage=IngestionStage(job.stage),
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            error_code=job.error_code,
            failure_reason=(f"Processing failed at {job.stage}." if job.error_code else None),
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            next_attempt_at=job.next_attempt_at,
        )

    async def delete_document(self, member: Membership, document_id: UUID) -> None:
        tenant = member.tenant_id
        async with self.sessions.begin() as session:
            # Claims update these same rows. Either a worker wins and deletion is
            # rejected, or deletion wins and a queued claim can no longer succeed.
            jobs = list(
                await session.scalars(
                    select(IngestionJob)
                    .where(
                        IngestionJob.tenant_id == tenant, IngestionJob.document_id == document_id
                    )
                    .order_by(IngestionJob.id)
                    .with_for_update()
                )
            )
            document = await self.originals._document(session, tenant, document_id)
            if document.status == DocumentStatus.DELETED:
                return
            if any(job.status == IngestionJobStatus.RUNNING for job in jobs):
                raise APIError(
                    409,
                    "document_processing",
                    "Wait for processing to finish before deleting this document.",
                )
            for job in jobs:
                if job.status == IngestionJobStatus.QUEUED:
                    job.status = IngestionJobStatus.CANCELLED
                    job.next_attempt_at = None
                    job.finished_at = datetime.now(UTC)
            if document.status != DocumentStatus.DELETING:
                self.audit(session, member, "document.delete_requested", "document", document_id)
            document.status = DocumentStatus.DELETING
        # No running job remains and no new job may be enqueued for this document.
        await self.index.delete_document(str(tenant), str(document_id))
        await asyncio.to_thread(self.originals.storage.delete, storage_key(tenant, document_id))
        artifacts = LocalArtifactStorage(self.settings.ingestion_artifact_root)
        for job in jobs:
            await asyncio.to_thread(artifacts.delete_job, tenant, job.id)
        async with self.sessions.begin() as session:
            document = await self.originals._document(session, tenant, document_id)
            if document.status != DocumentStatus.DELETED:
                document.status = DocumentStatus.DELETED
                document.deleted_at = datetime.now(UTC)
                document.error_message = None
                self.audit(session, member, "document.deleted", "document", document_id)
