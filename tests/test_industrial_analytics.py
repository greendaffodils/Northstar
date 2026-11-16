from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Equipment, FailureEvent, Organization
from app import seed_demo
from app.services.industrial_analytics import query_industrial


def test_seed_is_reproducible_and_analytics_are_tenant_scoped(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(seed_demo, "SessionLocal", factory)
    try:
        seeded = seed_demo.generate(as_of=date(2026, 11, 16), seed=20261116)
        assert seeded["status"] == "generated"
        assert seeded["counts"]["equipment"] == 80
        assert seeded["counts"]["failure_events"] == 1006
        assert seed_demo.generate(as_of=date(2026, 11, 16), seed=20261116)["status"] == "already_seeded"

        db = factory()
        org_id = seeded["organization_id"]
        failures = query_industrial(db, org_id, "Show failure history and root causes for M-204")
        assert failures["intent"] == "equipment_failure_history"
        assert len(failures["rows"]) >= 6
        assert {"Dust-contaminated grease and elevated vibration",
                "Coupling alignment remained outside tolerance after prior replacement"} <= {
            row["root_cause"] for row in failures["rows"]}
        parts = query_industrial(db, org_id, "What spare parts inventory is compatible with M-204?")
        assert parts["intent"] == "parts_inventory"
        assert {row["part_number"] for row in parts["rows"]} >= {"BRG-6205", "COUP-204", "SEAL-204"}

        other = Organization(id="other-org", name="Other tenant")
        db.add(other)
        db.flush()
        # Existing tenant's equipment and failure events cannot leak into another org's query.
        assert query_industrial(db, other.id, "Show failure history for M-204")["rows"] == []
        db.close()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
