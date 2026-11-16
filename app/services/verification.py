"""Deterministic checks for citation references and numeric support in generated text."""
import re

_CITATION = re.compile(r"\[S(\d+)\]")
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z])")


def verify_synthesis(question: str, text: str, evidence: list[dict]) -> dict:
    markers = [int(value) for value in _CITATION.findall(text)]
    valid_range = set(range(1, len(evidence) + 1))
    invalid_markers = sorted({value for value in markers if value not in valid_range})
    citation_ok = bool(evidence) and bool(markers) and not invalid_markers

    clean_text = _CITATION.sub("", text)
    allowed_numbers = set(_NUMBER.findall(question))
    for item in evidence:
        allowed_numbers.update(_NUMBER.findall(item.get("text", "")))
    claimed_numbers = set(_NUMBER.findall(clean_text))
    unsupported_numbers = sorted(claimed_numbers - allowed_numbers)
    numeric_ok = not unsupported_numbers
    return {"citation_references_valid": citation_ok,
            "invalid_citation_indices": invalid_markers,
            "numeric_values_supported": numeric_ok,
            "unsupported_numeric_values": unsupported_numbers}


def enforce_verification(question: str, result: dict, evidence: list[dict]) -> tuple[dict, dict]:
    """Fail closed on invalid markers or unsupported digit-form numbers."""
    validation = verify_synthesis(question, result.get("answer", ""), evidence)
    if result.get("grounded") and not (validation["citation_references_valid"] and validation["numeric_values_supported"]):
        result = {**result,
            "answer": "I could not verify the generated citations and numeric claims against the retrieved passages, so I am not presenting that synthesis.",
            "grounded": False,
            "citations": []}
    return result, validation
