from functools import lru_cache
import re
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import Chunk, Document

COLLECTION = "enterprise_chunks"
log = logging.getLogger("northstar.retrieval")
@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)
@lru_cache(maxsize=1)
def reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(settings.reranker_model)
@lru_cache(maxsize=1)
def qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=10)
def ensure_collection(client, dim: int):
    from qdrant_client import models
    if not client.collection_exists(COLLECTION):
        client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))
def embed_and_upsert(org_id, doc_id, ids, texts, filename, metadata=None):
    from qdrant_client import models
    vectors = embedder().encode(texts, normalize_embeddings=True).tolist()
    client, dim = qdrant(), len(vectors[0])
    ensure_collection(client, dim)
    chunk_metadata = metadata or [{} for _ in texts]
    client.upsert(COLLECTION, points=[models.PointStruct(id=cid, vector=v, payload={
        "org": org_id, "doc": doc_id, "filename": filename, "ordinal": i, "text": part,
        "equipment_ids": chunk_metadata[i].get("equipment_ids", []),
        "page": chunk_metadata[i].get("page"), "section": chunk_metadata[i].get("section"),
        "is_current": False,
    }) for i, (cid, v, part) in enumerate(zip(ids, vectors, texts))], wait=True)

def delete_vectors(ids: list[str]) -> None:
    if ids:
        from qdrant_client import models
        qdrant().delete(COLLECTION, points_selector=models.PointIdsList(points=ids), wait=True)

def delete_document_vectors(org_id: str, document_ids: list[str]) -> None:
    if document_ids:
        client = qdrant()
        if not client.collection_exists(COLLECTION):
            return
        from qdrant_client import models
        selector = models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="org", match=models.MatchValue(value=org_id)),
            models.FieldCondition(key="doc", match=models.MatchAny(any=document_ids)),
        ]))
        client.delete(COLLECTION, points_selector=selector, wait=True)

def set_document_current(org_id: str, document_ids: list[str], is_current: bool) -> None:
    if not document_ids:
        return
    client = qdrant()
    if not client.collection_exists(COLLECTION):
        return
    from qdrant_client import models
    selector = models.FilterSelector(filter=models.Filter(must=[
        models.FieldCondition(key="org", match=models.MatchValue(value=org_id)),
        models.FieldCondition(key="doc", match=models.MatchAny(any=document_ids)),
    ]))
    client.set_payload(COLLECTION, payload={"is_current": is_current}, points=selector, wait=True)

def eligible_chunks(db: Session, org_id: str, roles: tuple[str, ...] = (),
                    user_id: str | None = None) -> list[Chunk]:
    rows = db.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
        .where(Chunk.organization_id == org_id, Document.organization_id == org_id,
               Document.is_current.is_(True), Document.deleted_at.is_(None))).all()
    is_admin = "admin" in roles or "owner" in roles
    return [chunk for chunk, doc in rows if is_admin or "*" in doc.allowed_roles
            or bool(set(roles) & set(doc.allowed_roles)) or (user_id is not None and user_id in doc.allowed_user_ids)]

def search(db: Session, org_id: str, query: str, limit: int = 6, alpha: float | None = None,
           roles: tuple[str, ...] = (), user_id: str | None = None):
    from qdrant_client import models
    from rank_bm25 import BM25Okapi
    if alpha is None:
        alpha = settings.retrieval_dense_weight
    rows = eligible_chunks(db, org_id, roles, user_id)
    entity_ids = sorted(set(re.findall(r"\b[A-Z]{1,4}-\d{3,5}\b", query.upper())))
    if entity_ids:
        rows = [row for row in rows if set(row.metadata_json.get("equipment_ids", [])) & set(entity_ids)
                or any(entity_id in row.text.upper() for entity_id in entity_ids)]
    eligible_doc_ids = sorted({row.document_id for row in rows})
    must = [models.FieldCondition(key="org", match=models.MatchValue(value=org_id)),
            models.FieldCondition(key="is_current", match=models.MatchValue(value=True))]
    if eligible_doc_ids:
        must.append(models.FieldCondition(key="doc", match=models.MatchAny(any=eligible_doc_ids)))
    if entity_ids:
        must.append(models.FieldCondition(key="equipment_ids", match=models.MatchAny(any=entity_ids)))
    dense = []
    if eligible_doc_ids:
        try:
            model = embedder()
            vector = model.encode([query], normalize_embeddings=True)[0].tolist()
            client = qdrant()
            ensure_collection(client, len(vector))
            dense = client.query_points(COLLECTION, query=vector,
                query_filter=models.Filter(must=must),
                limit=limit * 3, with_payload=True,
                score_threshold=settings.retrieval_min_dense_score).points
        except Exception:
            log.exception("Dense retrieval unavailable; continuing with lexical retrieval")
    terms = query.lower().split()
    bm = BM25Okapi([row.text.lower().split() for row in rows]) if rows else None
    scores = bm.get_scores(terms) if bm else []
    lexical_order = [i for i in sorted(range(len(rows)), key=lambda j: scores[j], reverse=True)
                     if scores[i] > 0][:limit * 3] if rows else []
    lex = {rows[i].id: rank for rank, i in enumerate(lexical_order)}
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
    candidates = fused[:max(limit * 3, limit)]
    if settings.reranker_enabled and candidates:
        try:
            pairs = [(query, row.text) for _, row in candidates]
            rerank_scores = reranker().predict(pairs, show_progress_bar=False)
            reranked = [(float(rerank_score), rrf_score, row)
                        for rerank_score, (rrf_score, row) in zip(rerank_scores, candidates)]
            reranked.sort(key=lambda item: item[0], reverse=True)
            return [{"chunk_id": row.id, "document_id": row.document_id,
                     "filename": row.metadata_json.get("filename", ""),
                     "section": row.metadata_json.get("section", row.ordinal + 1),
                     "chunk_index": row.ordinal + 1, "page": row.metadata_json.get("page"),
                     "text": row.text, "score": round(rrf_score, 6),
                     "rerank_score": round(rerank_score, 6), "reranked": True}
                    for rerank_score, rrf_score, row in reranked[:limit]]
        except Exception:
            log.exception("Cross-encoder reranking failed; returning RRF ranking")
    return [{"chunk_id": row.id, "document_id": row.document_id,
             "filename": row.metadata_json.get("filename", ""),
             "section": row.metadata_json.get("section", row.ordinal + 1),
             "chunk_index": row.ordinal + 1, "page": row.metadata_json.get("page"),
             "text": row.text, "score": round(score, 6), "reranked": False}
            for score, row in candidates[:limit]]
