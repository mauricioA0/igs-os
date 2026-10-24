"""document_chunks: index the (tenant_id, vector_object_id) re-fetch path.

Hybrid search runs in two phases (igs_common.rag.pgvector_store): the dense/lexical phases return
a set of `vector_object_id`s, then `_rows` re-fetches the full chunk rows with
`WHERE tenant_id = :tid AND vector_object_id = ANY(:ids)`. There was no index supporting that
predicate, so every search did a seq scan of the tenant's chunks on the hot path. This adds a
composite index on (tenant_id, vector_object_id); partial on NOT NULL since only indexed chunks
carry a vector_object_id and that is exactly what the re-fetch binds.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_document_chunks_tenant_vobj",
        "document_chunks",
        ["tenant_id", "vector_object_id"],
        postgresql_where="vector_object_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_tenant_vobj", table_name="document_chunks")
