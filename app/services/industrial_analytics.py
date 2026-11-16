"""Allowlisted, parameterized industrial analytics. No user-provided SQL is executed."""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (Equipment, EquipmentCategory, EquipmentSparePart, FailureEvent,
                        Facility, Inventory, SparePart)


def _equipment(db: Session, organization_id: str, tag: str) -> Equipment | None:
    return db.scalar(select(Equipment).where(
        Equipment.organization_id == organization_id,
        func.lower(Equipment.equipment_tag) == tag.lower()))


def query_industrial(db: Session, organization_id: str, question: str) -> dict:
    """Route a small set of transparent questions to fixed SQLAlchemy query templates."""
    normalized = question.strip()
    tag_match = re.search(r"\b([A-Za-z]{1,3}-\d{2,4})\b", normalized)
    tag = tag_match.group(1).upper() if tag_match else None
    if not normalized:
        raise ValueError("question is required")

    if any(word in normalized.lower() for word in ("inventory", "spare part", "parts stock", "stock for")):
        if not tag:
            return {"intent": "parts_inventory", "answer": "Specify an equipment tag, for example M-204.",
                    "columns": [], "rows": [], "calculations": [], "data_basis": "organization-scoped inventory"}
        item = _equipment(db, organization_id, tag)
        if not item:
            return {"intent": "parts_inventory", "answer": f"No equipment tagged {tag} was found.",
                    "columns": ["equipment_tag", "part_number", "part_name", "facility", "quantity", "reorder_level"],
                    "rows": [], "calculations": [], "data_basis": "organization-scoped inventory"}
        rows = db.execute(select(SparePart.part_number, SparePart.name, Facility.name,
                Inventory.quantity_available, Inventory.reorder_level)
            .join(EquipmentSparePart, EquipmentSparePart.spare_part_id == SparePart.id)
            .join(Inventory, Inventory.spare_part_id == SparePart.id)
            .join(Facility, Facility.id == Inventory.facility_id)
            .where(EquipmentSparePart.organization_id == organization_id,
                EquipmentSparePart.equipment_id == item.id,
                SparePart.organization_id == organization_id,
                Inventory.organization_id == organization_id,
                Facility.organization_id == organization_id)
            .order_by(Facility.name, SparePart.part_number)).all()
        data = [{"equipment_tag": tag, "part_number": r[0], "part_name": r[1], "facility": r[2],
                 "quantity": r[3], "reorder_level": r[4], "below_reorder": r[3] < r[4]} for r in rows]
        return {"intent": "parts_inventory", "answer": f"Found {len(data)} compatible stocked part locations for {tag}.",
                "columns": list(data[0].keys()) if data else ["equipment_tag", "part_number", "part_name", "facility", "quantity", "reorder_level", "below_reorder"],
                "rows": data, "calculations": [], "data_basis": "organization-scoped compatible parts and facility inventory"}

    if tag and any(word in normalized.lower() for word in ("failure", "breakdown", "root cause", "downtime", "history")):
        item = _equipment(db, organization_id, tag)
        if not item:
            data = []
        else:
            since = datetime.now(timezone.utc) - timedelta(days=90)
            results = db.execute(select(FailureEvent.incident_code, FailureEvent.occurred_at,
                    FailureEvent.failure_mode, FailureEvent.root_cause, FailureEvent.downtime_minutes,
                    FailureEvent.severity)
                .where(FailureEvent.organization_id == organization_id,
                    FailureEvent.equipment_id == item.id, FailureEvent.occurred_at >= since)
                .order_by(FailureEvent.occurred_at.desc())).all()
            data = [{"incident_code": r[0], "occurred_at": r[1].isoformat(), "failure_mode": r[2],
                     "root_cause": r[3], "downtime_minutes": r[4], "severity": r[5]} for r in results]
        return {"intent": "equipment_failure_history", "answer": f"Found {len(data)} failure events for {tag} in the last 90 days.",
                "columns": ["incident_code", "occurred_at", "failure_mode", "root_cause", "downtime_minutes", "severity"],
                "rows": data, "calculations": [{"name": "window_days", "value": 90}],
                "data_basis": "organization-scoped failure events; rolling 90-day window"}

    if any(word in normalized.lower() for word in ("downtime", "lost time")):
        since = datetime.now(timezone.utc) - timedelta(days=90)
        rows = db.execute(select(EquipmentCategory.name, func.count(FailureEvent.id),
                    func.coalesce(func.sum(FailureEvent.downtime_minutes), 0))
            .join(Equipment, Equipment.category_id == EquipmentCategory.id)
            .outerjoin(FailureEvent, (FailureEvent.equipment_id == Equipment.id) &
                (FailureEvent.organization_id == organization_id) & (FailureEvent.occurred_at >= since))
            .where(Equipment.organization_id == organization_id,
                EquipmentCategory.organization_id == organization_id)
            .group_by(EquipmentCategory.name).order_by(func.sum(FailureEvent.downtime_minutes).desc())).all()
        data = [{"category": r[0], "failure_count": r[1], "downtime_minutes": int(r[2])} for r in rows]
        return {"intent": "downtime_by_category", "answer": "Summarized recorded downtime by equipment category over the last 90 days.",
                "columns": ["category", "failure_count", "downtime_minutes"], "rows": data,
                "calculations": [{"name": "window_days", "value": 90}],
                "data_basis": "organization-scoped failure events; rolling 90-day window"}

    return {"intent": "unsupported", "answer": "I can answer equipment failure history (by tag), compatible spare-part inventory (by tag), or downtime by equipment category.",
            "columns": [], "rows": [], "calculations": [],
            "data_basis": "No query was run; request did not match an available analytical operation."}
