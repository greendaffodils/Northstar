"""Reconcile one tenant's eligible SQL chunks with Qdrant; mutation requires --apply."""
import argparse
import json

from app.core.db import SessionLocal
from app.services.vector_reconciliation import reconcile_organization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--apply", action="store_true", help="upsert missing vectors and delete tenant orphan vectors")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        print(json.dumps(reconcile_organization(db, args.organization_id, apply=args.apply), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
