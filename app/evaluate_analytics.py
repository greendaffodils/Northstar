"""Run the small, versioned analytics routing and expected-row evaluation set."""
import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.services.industrial_analytics import query_industrial


def evaluate(db: Session, organization_id: str, cases_path: Path) -> dict:
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for case in cases:
        actual = query_industrial(db, organization_id, case["question"])
        row_values = {str(value) for row in actual["rows"] for value in row.values()}
        expected_values = set(case.get("required_row_values", []))
        results.append({"id": case["id"], "expected_intent": case["expected_intent"],
            "actual_intent": actual["intent"], "intent_match": actual["intent"] == case["expected_intent"],
            "required_values_match": expected_values <= row_values,
            "missing_values": sorted(expected_values - row_values)})
    total = len(results)
    intent_matches = sum(item["intent_match"] for item in results)
    value_matches = sum(item["required_values_match"] for item in results)
    return {"cases": total, "intent_accuracy": intent_matches / total if total else 0,
            "required_value_pass_rate": value_matches / total if total else 0,
            "results": results,
            "limitation": "Small deterministic analytics routing check; not a broad RAG, answer-quality, or production benchmark."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--cases", type=Path, default=Path("evals/industrial_analytics.jsonl"))
    args = parser.parse_args()
    db = SessionLocal()
    try:
        print(json.dumps(evaluate(db, args.organization_id, args.cases), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
