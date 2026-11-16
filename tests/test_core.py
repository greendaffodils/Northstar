import pytest
from app.services.ingestion import split_chunks, extract, validate_content
from app.core.config import Settings

def test_text_chunking_keeps_overlap_and_content():
    text = "Sentence one. " * 180
    chunks = split_chunks(text, size=300, overlap=40)
    assert len(chunks) > 1
    assert all(chunks)
    assert chunks[0][-25:] in chunks[1]

def test_csv_extraction_tracks_dimensions():
    text, meta = extract("sales.csv", b"region,revenue\nwest,42\n")
    assert "west | 42" in text
    assert meta == {"rows": 2, "columns": 2}

def test_rejects_extension_content_mismatch():
    with pytest.raises(ValueError, match="valid PDF"):
        validate_content("manual.pdf", b"not a pdf")

def test_rejects_invalid_utf8_text():
    with pytest.raises(ValueError, match="UTF-8"):
        validate_content("notes.txt", b"\xff\xfe\x00")

def test_production_rejects_development_secrets():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret="insecure-development-secret-change-me",
                 bootstrap_password="a-strong-password-value")
