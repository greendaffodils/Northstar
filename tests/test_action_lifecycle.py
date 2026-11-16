from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.services.action_execution import approve_action, execute_simulated, reject_action
from app.models import ActionRequest, Equipment, EquipmentCategory, Facility, Organization, User, WorkOrder


def test_approved_work_order_action_executes_idempotently(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        org = Organization(id="org-1", name="Demo")
        user = User(id="user-1", organization_id=org.id, email="admin@example.com",
                    password_hash="unused", role="admin")
        facility = Facility(id="facility-1", organization_id=org.id, name="Plant", region="North")
        category = EquipmentCategory(id="category-1", organization_id=org.id, name="Motor")
        equipment = Equipment(id="equipment-1", organization_id=org.id, facility_id=facility.id,
            category_id=category.id, equipment_tag="M-204", name="Motor", manufacturer="Example",
            model="M1", commissioned_at=datetime.now(timezone.utc), criticality="high")
        db.add_all([org, user, facility, category, equipment])
        db.commit()

        action = ActionRequest(id="action-1", organization_id=org.id, requested_by=user.id,
            kind="work_order", payload={"equipment_tag": "M-204", "description": "Inspect drive end bearing",
            "priority": "high"}, status="pending_approval", idempotency_key="key-1", execution_result={})
        db.add(action); db.commit()
        with pytest.raises(HTTPException) as before_approval:
            execute_simulated(action.id, org.id, user.id, db)
        assert before_approval.value.status_code == 409

        approved = approve_action(action.id, org.id, user.id, db)
        assert approved["status"] == "approved"
        first = execute_simulated(action.id, org.id, user.id, db)
        second = execute_simulated(action.id, org.id, user.id, db)
        assert first["status"] == "executed" and not first["deduplicated"]
        assert second["deduplicated"] is True
        assert first["result"]["simulated"] is True
        assert db.scalar(select(WorkOrder).where(WorkOrder.organization_id == org.id)).id == first["result"]["work_order_id"]
        assert db.scalar(select(ActionRequest).where(ActionRequest.id == action.id)).status == "executed"
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_rejected_action_cannot_execute():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        org = Organization(id="org-1", name="Demo")
        user = User(id="user-1", organization_id=org.id, email="admin@example.com",
                    password_hash="unused", role="admin")
        db.add_all([org, user]); db.commit()
        action = ActionRequest(id="action-1", organization_id=org.id, requested_by=user.id,
            kind="report", payload={}, status="pending_approval", idempotency_key="key-1", execution_result={})
        db.add(action); db.commit()
        assert reject_action(action.id, org.id, user.id, db)["status"] == "rejected"
        with pytest.raises(HTTPException) as rejected:
            execute_simulated(action.id, org.id, user.id, db)
        assert rejected.value.status_code == 409
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
