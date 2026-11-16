"""Review and run local simulated action adapters with tenant and idempotency checks."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActionRequest, AuditEvent, Equipment, WorkOrder


def approve_action(action_id: str, organization_id: str, actor_id: str, db: Session) -> dict:
    action = db.scalar(select(ActionRequest).where(ActionRequest.id == action_id,
        ActionRequest.organization_id == organization_id))
    if not action:
        raise HTTPException(404, "Action not found")
    if action.status != "pending_approval":
        raise HTTPException(409, "Action is not pending")
    action.status = "approved"
    db.add(AuditEvent(id=str(uuid4()), organization_id=organization_id, actor_id=actor_id,
        event_type="action.approved", details={"action_id": action.id}))
    db.commit()
    return {"id": action.id, "status": action.status,
            "message": "Approved. An administrator may now run the simulated adapter."}


def reject_action(action_id: str, organization_id: str, actor_id: str, db: Session) -> dict:
    action = db.scalar(select(ActionRequest).where(ActionRequest.id == action_id,
        ActionRequest.organization_id == organization_id))
    if not action:
        raise HTTPException(404, "Action not found")
    if action.status != "pending_approval":
        raise HTTPException(409, "Action is not pending")
    action.status = "rejected"
    db.add(AuditEvent(id=str(uuid4()), organization_id=organization_id, actor_id=actor_id,
        event_type="action.rejected", details={"action_id": action.id}))
    db.commit()
    return {"id": action.id, "status": action.status}


def execute_simulated(action_id: str, organization_id: str, actor_id: str, db: Session) -> dict:
    action = db.scalar(select(ActionRequest).where(ActionRequest.id == action_id,
        ActionRequest.organization_id == organization_id))
    if not action:
        raise HTTPException(404, "Action not found")
    if action.status == "executed":
        return {"id": action.id, "status": action.status, "result": action.execution_result,
                "deduplicated": True}
    if action.status != "approved":
        raise HTTPException(409, "Only approved actions can execute")
    result = {"simulated": True, "adapter": "local-demo", "idempotency_key": action.idempotency_key}
    if action.kind == "work_order":
        payload = action.payload
        equipment = db.scalar(select(Equipment).where(Equipment.organization_id == organization_id,
            Equipment.equipment_tag == payload["equipment_tag"]))
        if not equipment:
            raise HTTPException(404, "Equipment not found in this organization")
        work_order = db.scalar(select(WorkOrder).where(WorkOrder.organization_id == organization_id,
            WorkOrder.idempotency_key == action.id))
        if not work_order:
            work_order = WorkOrder(id=str(uuid4()), organization_id=organization_id,
                equipment_id=equipment.id, failure_event_id=None, requested_by=action.requested_by,
                idempotency_key=action.id, description=payload["description"].strip(),
                priority=payload.get("priority", "normal"), status="open",
                estimated_cost=float(payload.get("estimated_cost", 0) or 0))
            db.add(work_order)
            db.flush()
        result["work_order_id"] = work_order.id
    action.status, action.execution_result = "executed", result
    db.add(AuditEvent(id=str(uuid4()), organization_id=organization_id, actor_id=actor_id,
        event_type="action.executed", details={"action_id": action.id, "kind": action.kind,
        "simulated": True, "result": result}))
    db.commit()
    return {"id": action.id, "status": action.status, "result": result, "deduplicated": False}
