"""document_chunks: payload for vector-store filters; title joins the keyword index.

The RAG store (`igs_common.rag.pgvector_store`) keeps each chunk's filter/store fields
(title, source, account, dates…) in `payload`, mirroring the Vertex Vector Search data
object. `tsv` is regenerated so keyword search also matches the chunk's title.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV_WITH_TITLE = "to_tsvector('simple', coalesce(payload->>'title', '') || ' ' || content)"
TSV_CONTENT_ONLY = "to_tsvector('simple', content)"


def _replace_tsv(expression: str) -> None:
    op.drop_index("ix_document_chunks_tsv", table_name="document_chunks", postgresql_using="gin")
    op.drop_column("document_chunks", "tsv")
    op.add_column(
        "document_chunks",
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["tsv"], postgresql_using="gin")


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("payload", postgresql.JSONB(), nullable=True))
    op.create_index(
        "ix_document_chunks_payload",
        "document_chunks",
        ["payload"],
        postgresql_using="gin",
        postgresql_ops={"payload": "jsonb_path_ops"},
    )
    _replace_tsv(TSV_WITH_TITLE)


def downgrade() -> None:
    _replace_tsv(TSV_CONTENT_ONLY)
    op.drop_index(
        "ix_document_chunks_payload", table_name="document_chunks", postgresql_using="gin"
    )
    op.drop_column("document_chunks", "payload")
