"""Retrieval for IGS OS: documents and Account 360 interactions behind one `VectorStore`.

See docs/architecture/rag.md. Stores: `PgVectorStore` (default, local and fallback),
`VertexVectorStore` (Agent Retrieval), `InMemoryStore` (tests, dry-run evals).
"""

from igs_common.rag.defaults import default_retriever, retrieve, search_knowledge
from igs_common.rag.embed import (
    Embedder,
    HashEmbedder,
    HttpEmbedder,
    HttpReranker,
    OverlapReranker,
    Reranker,
)
from igs_common.rag.filters import FilterError, with_tenant
from igs_common.rag.fusion import rrf
from igs_common.rag.pgvector_store import PgVectorStore
from igs_common.rag.retrieve import Retriever
from igs_common.rag.store import InMemoryStore, VectorStore
from igs_common.rag.types import (
    Chunk,
    Citation,
    Filter,
    Hit,
    RetrievalResult,
    SearchRequest,
    SearchResult,
    SparseVector,
    make_chunk_id,
)
from igs_common.rag.vertex_store import VertexVectorStore

__all__ = [
    "default_retriever",
    "retrieve",
    "search_knowledge",
    "Chunk",
    "Citation",
    "Embedder",
    "Filter",
    "FilterError",
    "HashEmbedder",
    "Hit",
    "HttpEmbedder",
    "HttpReranker",
    "InMemoryStore",
    "OverlapReranker",
    "PgVectorStore",
    "Reranker",
    "RetrievalResult",
    "Retriever",
    "SearchRequest",
    "SearchResult",
    "SparseVector",
    "VectorStore",
    "VertexVectorStore",
    "make_chunk_id",
    "rrf",
    "with_tenant",
]
