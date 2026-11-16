import csv
import io
import re
import zipfile
from pathlib import Path
from uuid import uuid4

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
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("Only PDF, DOCX, CSV, and TXT files are supported")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(p.extract_text() or "" for p in reader.pages), {"pages": len(reader.pages)}
    if ext == ".docx":
        from docx import Document as DocxDocument
        doc = DocxDocument(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs), {"paragraphs": len(doc.paragraphs)}
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        return "\n".join(" | ".join(row) for row in rows), {"rows": len(rows), "columns": len(rows[0]) if rows else 0}
    return raw.decode("utf-8-sig"), {}

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

def ingest(document_id: str, raw: bytes):
    from app.core.db import SessionLocal
    from app.models import Chunk, Document
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.status = "processing"
        db.commit()
        text, meta = extract(doc.filename, raw)
        parts = split_chunks(text)
        ids = [str(uuid4()) for _ in parts]
        for i, (cid, part) in enumerate(zip(ids, parts)):
            db.add(Chunk(id=cid, document_id=doc.id, organization_id=doc.organization_id,
                         ordinal=i, text=part, metadata_json={**meta, "filename": doc.filename}))
        db.commit()
        if parts:
            from app.services.retrieval import embed_and_upsert
            embed_and_upsert(doc.organization_id, doc.id, ids, parts, doc.filename)
        doc.status, doc.error = "ready", None
        db.commit()
    except Exception as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.status, doc.error = "failed", str(exc)[:1000]
            db.commit()
    finally:
        db.close()
