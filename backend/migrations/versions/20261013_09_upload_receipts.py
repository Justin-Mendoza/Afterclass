"""Add durable upload retry receipts.

Revision ID: 20261013_09
Revises: 20260918_08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_09"
down_revision: str | None = "20260918_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ingestion_jobs_tenant_id_id", "ingestion_jobs", ["tenant_id", "id"]
    )
    op.create_table(
        "upload_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "collection_id", "membership_id", "key"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "collection_id"], ["collections.tenant_id", "collections.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"], ["memberships.tenant_id", "memberships.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.id"]
        ),
    )


def downgrade() -> None:
    op.drop_table("upload_receipts")
    op.drop_constraint("uq_ingestion_jobs_tenant_id_id", "ingestion_jobs", type_="unique")
