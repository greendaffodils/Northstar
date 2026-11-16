"""Find and optionally repair vector/index drift for one organization."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document


def classify_drift(expected_ids: set[str], vector_ids: set[str]) -> tuple[set[str], set[str]]:
    """Return SQL chunks missing from Qdrant and Qdrant IDs absent from eligible SQL."""
    return expected_ids - vector_ids, vector_ids - expected_ids


def reconcile_organization(db: Session, organization_id: str, *, apply: bool = False, client=None) -> dict:
    """Compare current ready SQL chunks to Qdrant points filtered to a single tenant."""
    from qdrant_client import models

    if client is None:
        from app.services.retrieval import qdrant
        client = qdrant()
    from app.services.retrieval import COLLECTION, delete_vectors, embed_and_upsert, set_document_current

    rows = db.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
        .where(Chunk.organization_id == organization_id, Document.organization_id == organization_id,
            Document.status == "ready", Document.is_current.is_(True), Document.deleted_at.is_(None))).all()
    expected = {chunk.id: (chunk, doc) for chunk, doc in rows}
    if not client.collection_exists(COLLECTION):
        vector_ids = set()
    else:
        query_filter = models.Filter(must=[models.FieldCondition(key="org",
            match=models.MatchValue(value=organization_id))])
        vector_ids, offset = set(), None
        while True:
            points, offset = client.scroll(COLLECTION, scroll_filter=query_filter, limit=256,
                offset=offset, with_payload=False, with_vectors=False)
            vector_ids.update(str(point.id) for point in points)
            if offset is None:
                break

    missing, orphaned = classify_drift(set(expected), vector_ids)
    repaired = {"upserted": 0, "deleted": 0}
    if apply:
        by_document = {}
        for chunk_id in missing:
            chunk, document = expected[chunk_id]
            by_document.setdefault(document.id, (document, []))[1].append(chunk)
        document_ids = []
        for document_id, (document, chunks) in by_document.items():
            chunks.sort(key=lambda chunk: chunk.ordinal)
            embed_and_upsert(organization_id, document_id, [chunk.id for chunk in chunks],
                [chunk.text for chunk in chunks], document.filename,
                [chunk.metadata_json for chunk in chunks])
            document_ids.append(document_id)
            repaired["upserted"] += len(chunks)
        if document_ids:
            set_document_current(organization_id, document_ids, True)
        if orphaned:
            delete_vectors(sorted(orphaned))
            repaired["deleted"] = len(orphaned)

    return {"organization_id": organization_id, "eligible_sql_chunks": len(expected),
            "tenant_qdrant_vectors": len(vector_ids), "missing_vector_ids": sorted(missing),
            "orphaned_vector_ids": sorted(orphaned), "apply": apply, "repaired": repaired}
