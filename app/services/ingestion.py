import csv
import io
import re
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import delete, select
from app.core.db import SessionLocal
from app.core.config import settings
from app.models import Chunk, Document, IngestionJob

ALLOWED = {".pdf", ".docx", ".csv", ".txt"}

def validate_content(filename: str, raw: bytes) -> None:
    """Reject files whose bytes do not match the supported extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ValueError("File content is not a valid PDF")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise ValueError("DOCX package is missing required document parts")
        except zipfile.BadZipFile as exc:
            raise ValueError("File content is not a valid DOCX document") from exc
    if ext in {".csv", ".txt"}:
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV and TXT files must use UTF-8 encoding") from exc

def extract(filename: str, raw: bytes) -> tuple[str, dict]:
    segments = extract_segments(filename, raw)
    text = "\n".join(item[0] for item in segments)
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        return text, {"rows": len(rows), "columns": len(rows[0]) if rows else 0}
    meta = {"source_extension": ext, "segments": len(segments)}
    if ext == ".pdf":
        meta["pages"] = len(segments)
    elif ext == ".docx":
        meta["paragraphs"] = sum(item[1].get("paragraphs", 0) for item in segments)
    return text, meta

def extract_segments(filename: str, raw: bytes) -> list[tuple[str, dict]]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("Only PDF, DOCX, CSV, and TXT files are supported")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return [(page.extract_text() or "", {"page": number, "section": f"Page {number}"})
                for number, page in enumerate(reader.pages, start=1)]
    if ext == ".docx":
        from docx import Document as DocxDocument
        doc = DocxDocument(io.BytesIO(raw))
        groups, heading, blocks, paragraph_count = [], "Document", [], 0
        def flush():
            if blocks:
                groups.append(("\n".join(blocks), {"section": heading, "paragraphs": paragraph_count}))
        for paragraph in doc.paragraphs:
            content = paragraph.text.strip()
            if not content:
                continue
            style = paragraph.style.name if paragraph.style else ""
            if style.lower().startswith("heading"):
                flush()
                heading = content
                blocks, paragraph_count = [], 0
            else:
                blocks.append(content)
                paragraph_count += 1
        for table_index, table in enumerate(doc.tables, start=1):
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            groups.append(("\n".join(rows), {"section": heading, "block_type": "table",
                                              "table": table_index, "rows": len(rows)}))
        flush()
        return groups
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        if not rows:
            return []
        header, data = rows[0], rows[1:]
        groups = []
        for offset in range(0, max(len(data), 1), 20):
            selected = data[offset:offset + 20]
            table_rows = [header, *selected]
            groups.append(("\n".join(" | ".join(row) for row in table_rows),
                           {"block_type": "table", "header": header,
                            "row_start": offset + 2, "rows": len(selected) + 1, "columns": len(header)}))
        return groups
    content = raw.decode("utf-8-sig")
    return [(part.strip(), {"section": f"Paragraph {index}"})
            for index, part in enumerate(re.split(r"\n\s*\n", content), start=1) if part.strip()]

def split_chunks(text: str, size: int = 1100, overlap: int = 160) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            pivot = text.rfind(". ", start + size // 2, end)
            if pivot > start:
                end = pivot + 1
        chunks.append(text[start:end].strip())
        start = max(end - overlap, start + 1)
    return [part for part in chunks if part]

def process_job(job_id: str) -> None:
    """Run one claimed job. SQL state is authoritative; vector writes are replay-safe."""
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job or job.status != "running":
            return
        if job.job_type == "delete_vectors":
            from app.services.retrieval import delete_document_vectors
            document_ids = job.payload.get("document_ids", [])
            delete_document_vectors(job.organization_id, document_ids)
            org_dir = (Path(settings.upload_dir) / job.organization_id).resolve()
            for name in job.payload.get("storage_paths", []):
                path = Path(name).resolve()
                if path.is_relative_to(org_dir):
                    path.unlink(missing_ok=True)
            job.status, job.progress, job.last_error, job.locked_at = "completed", 100, None, None
            db.commit()
            return
        doc = db.scalar(select(Document).where(Document.id == job.document_id,
                                               Document.organization_id == job.organization_id))
        if not doc or doc.deleted_at is not None:
            job.status = "cancelled"
            job.last_error = "Document is missing or has been deleted"
            db.commit()
            return
        doc.status = "processing"
        job.progress = 10
        db.commit()
        raw = Path(doc.storage_path).read_bytes()
        validate_content(doc.filename, raw)
        segments = extract_segments(doc.filename, raw)
        text = "\n".join(value for value, _ in segments)
        equipment_ids = sorted(set(re.findall(r"\b[A-Z]{1,4}-\d{3,5}\b", text.upper())))
        doc.metadata_json = {"title": Path(doc.filename).stem, "source_extension": Path(doc.filename).suffix.lower(),
                             "content_sha256": doc.content_hash, "equipment_ids": equipment_ids,
                             "segments": len(segments)}
        parts, chunk_metadata = [], []
        for segment, segment_meta in segments:
            for piece in split_chunks(segment):
                parts.append(piece)
                chunk_metadata.append({**segment_meta, "equipment_ids": equipment_ids})
        ids = [str(uuid5(NAMESPACE_URL, f"northstar:{doc.id}:{i}:{part}")) for i, part in enumerate(parts)]
        job.progress = 35
        db.commit()
        if parts:
            from app.services.retrieval import embed_and_upsert
            embed_and_upsert(doc.organization_id, doc.id, ids, parts, doc.filename, chunk_metadata)
        job.progress = 75
        db.commit()
        job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id).with_for_update())
        doc = db.scalar(select(Document).where(Document.id == job.document_id,
            Document.organization_id == job.organization_id).with_for_update()) if job else None
        if not job or job.status != "running" or not doc or doc.deleted_at is not None:
            if ids:
                from app.services.retrieval import delete_vectors
                delete_vectors(ids)
            return
        old_ids = list(db.scalars(select(Chunk.id).where(Chunk.document_id == doc.id)))
        db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        for i, (cid, part) in enumerate(zip(ids, parts)):
            db.add(Chunk(id=cid, document_id=doc.id, organization_id=doc.organization_id,
                         ordinal=i, text=part, metadata_json={**chunk_metadata[i], "filename": doc.filename}))
        current_versions = db.scalars(select(Document).where(
            Document.organization_id == doc.organization_id,
            Document.family_id == doc.family_id,
            Document.id != doc.id,
            Document.is_current.is_(True),
            Document.deleted_at.is_(None))).all()
        newer_is_current = any(item.version > doc.version for item in current_versions)
        if newer_is_current:
            doc.status, doc.error, doc.is_current = "superseded", None, False
            true_ids = []
            false_ids = [doc.id]
        else:
            for old in current_versions:
                old.is_current = False
                old.status = "superseded"
            doc.status, doc.error, doc.is_current = "ready", None, True
            true_ids = [doc.id]
            false_ids = [old.id for old in current_versions]
        cleanup_ids = sorted(set(job.cleanup_vector_ids or []) | {old_id for old_id in old_ids if old_id not in ids})
        pending = job.payload_updates or {}
        pending_true = set(pending.get("true", [])) | set(true_ids)
        pending_false = set(pending.get("false", [])) | set(false_ids)
        pending_true -= pending_false
        job.status, job.progress, job.last_error, job.locked_at = "completed", 100, None, None
        job.cleanup_vector_ids = cleanup_ids
        job.payload_updates = {"true": sorted(pending_true), "false": sorted(pending_false)}
        db.commit()
        if pending_false or pending_true:
            from app.services.retrieval import set_document_current
            set_document_current(doc.organization_id, sorted(pending_false), False)
            set_document_current(doc.organization_id, sorted(pending_true), True)
            job.payload_updates = {}
            db.commit()
        if cleanup_ids:
            from app.services.retrieval import delete_vectors
            delete_vectors(cleanup_ids)
            job.cleanup_vector_ids = []
            db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        if job:
            if job.status == "cancelled":
                db.commit()
                return
            job.last_error = str(exc)[:1000]
            job.locked_at = None
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                job.progress = 0
                doc = db.get(Document, job.document_id)
                if doc:
                    has_chunks = db.scalar(select(Chunk.id).where(Chunk.document_id == doc.id).limit(1)) is not None
                    doc.status = "ready" if doc.is_current and has_chunks else "failed"
                    doc.error = job.last_error
            else:
                job.status = "retrying"
                delay = min(2 ** max(job.attempts - 1, 0), 300)
                job.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                doc = db.get(Document, job.document_id)
                if doc:
                    has_chunks = db.scalar(select(Chunk.id).where(Chunk.document_id == doc.id).limit(1)) is not None
                    doc.status = "ready" if doc.is_current and has_chunks else "queued"
                    doc.error = job.last_error
            db.commit()
    finally:
        db.close()
