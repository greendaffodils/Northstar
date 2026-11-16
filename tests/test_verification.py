from app.services.verification import enforce_verification, verify_synthesis


def test_verifier_accepts_retrieved_marker_and_supported_digits():
    evidence = [{"text": "Motor M-204 failed 3 times and lost 240 minutes.", "document_id": "doc-1"}]
    result = verify_synthesis("What happened to M-204?", "M-204 failed 3 times [S1].", evidence)
    assert result["citation_references_valid"] is True
    assert result["numeric_values_supported"] is True


def test_verifier_rejects_unknown_citations_and_unsupported_numbers():
    evidence = [{"text": "Motor M-204 failed 3 times.", "document_id": "doc-1"}]
    response, validation = enforce_verification("Why did M-204 fail?", {
        "answer": "It failed 9 times [S2].", "citations": [], "grounded": True}, evidence)
    assert validation["citation_references_valid"] is False
    assert validation["numeric_values_supported"] is False
    assert response["grounded"] is False
    assert response["citations"] == []
    assert "could not verify" in response["answer"]


def test_verifier_does_not_change_unconfigured_non_synthesis():
    response, validation = enforce_verification("M-204 status", {
        "answer": "LLM is not configured.", "citations": [], "grounded": False}, [])
    assert response["grounded"] is False
    assert response["answer"] == "LLM is not configured."
    assert validation["citation_references_valid"] is False
