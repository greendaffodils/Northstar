import pytest
from app.services.ingestion import split_chunks, extract, extract_segments, validate_content
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

def test_text_extraction_preserves_paragraph_boundaries():
    segments = extract_segments("manual.txt", b"First procedure paragraph.\n\nSecond section text.")
    assert segments == [("First procedure paragraph.", {"section": "Paragraph 1"}),
                        ("Second section text.", {"section": "Paragraph 2"})]

def test_csv_extraction_keeps_header_with_each_table_block():
    raw = ("id,value\n" + "\n".join(f"{i},{i * 10}" for i in range(25))).encode()
    segments = extract_segments("metrics.csv", raw)
    assert len(segments) == 2
    assert segments[0][0].splitlines()[0] == "id | value"
    assert segments[1][0].splitlines()[0] == "id | value"
    assert segments[1][1]["row_start"] == 22
