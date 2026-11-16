from functools import lru_cache
from sqlalchemy import select
from sqlalchemy.orm import Session
from rank_bm25 import BM25Okapi
from app.core.config import settings
from app.models import Chunk, Document

COLLECTION = "enterprise_chunks"
@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)
@lru_cache(maxsize=1)
def qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=10)
def ensure_collection(client, dim: int):
    from qdrant_client import models
    if not client.collection_exists(COLLECTION):
        client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))
def embed_and_upsert(org_id, doc_id, ids, texts, filename):
    from qdrant_client import models
    vectors = embedder().encode(texts, normalize_embeddings=True).tolist()
    client, dim = qdrant(), len(vectors[0])
    ensure_collection(client, dim)
    client.upsert(COLLECTION, points=[models.PointStruct(id=cid, vector=v, payload={"org": org_id, "doc": doc_id, "filename": filename, "ordinal": i, "text": part}) for i, (cid, v, part) in enumerate(zip(ids, vectors, texts))], wait=True)
def search(db: Session, org_id: str, query: str, limit: int = 6, alpha: float = .55):
    from qdrant_client import models
    model = embedder()
    vector = model.encode([query], normalize_embeddings=True)[0].tolist()
    client = qdrant()
    try:
        ensure_collection(client, len(vector))
        dense = client.query_points(COLLECTION, query=vector,
            query_filter=models.Filter(must=[models.FieldCondition(key="org", match=models.MatchValue(value=org_id))]),
            limit=limit * 3, with_payload=True).points
    except Exception:
        # Preserve lexical retrieval when the vector service is temporarily unavailable.
        dense = []
    rows = list(db.scalars(select(Chunk).join(Document, Chunk.document_id == Document.id)
                           .where(Chunk.organization_id == org_id,
                                  Document.organization_id == org_id,
                                  Document.status == "ready")))
    terms = query.lower().split()
    bm = BM25Okapi([row.text.lower().split() for row in rows]) if rows else None
    scores = bm.get_scores(terms) if bm else []
    lex = {rows[i].id: rank for rank, i in enumerate(sorted(range(len(rows)), key=lambda j: scores[j], reverse=True)[:limit * 3])} if rows else {}
    dense_rank = {str(point.id): i for i, point in enumerate(dense)}
    by_id = {row.id: row for row in rows}
    fused = []
    for cid in set(dense_rank) | set(lex):
        score = (alpha / (60 + dense_rank[cid] + 1) if cid in dense_rank else 0)
        score += ((1 - alpha) / (60 + lex[cid] + 1) if cid in lex else 0)
        row = by_id.get(cid)
        if row:
            fused.append((score, row))
    fused.sort(key=lambda pair: pair[0], reverse=True)
    return [{"chunk_id": r.id, "document_id": r.document_id,
             "filename": r.metadata_json.get("filename", ""), "section": r.ordinal + 1,
             "text": r.text, "score": round(score, 6)} for score, r in fused[:limit]]
