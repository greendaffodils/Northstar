"""Generate a deterministic synthetic industrial organization for local demos."""
import argparse
import random
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import (
    Organization, Facility, EquipmentCategory, Technician, Equipment, FailureEvent,
    WorkOrder, MaintenanceLog, SparePart, EquipmentSparePart, Inventory,
    OperationalMetric, SafetyIncident, SyntheticDatasetManifest,
)

SEED = 20261116
DATASET = "aster-ridge-industrial-v1"
GENERATOR_VERSION = "1.0.0"
PROVENANCE = ("Entirely synthetic, deterministically generated demonstration data. "
              "These records are not measurements or reports from a real facility.")

def stable_id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"northstar:{DATASET}:{kind}:{value}"))

def generate(as_of: date = date(2026, 11, 16), seed: int = SEED) -> dict:
    rng = random.Random(seed)
    as_of_dt = datetime.combine(as_of, time(12), tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).order_by(Organization.id).limit(1))
        if not org:
            org = Organization(id=stable_id("org", "aster-ridge"),
                               name="Aster Ridge Manufacturing (Synthetic Demo)")
            db.add(org); db.flush()
        existing = db.scalar(select(SyntheticDatasetManifest).where(
            SyntheticDatasetManifest.organization_id == org.id,
            SyntheticDatasetManifest.dataset_name == DATASET))
        if existing:
            return {"status": "already_seeded", "organization_id": org.id,
                    "dataset": existing.dataset_name, "counts": existing.record_counts}
        if db.scalar(select(Equipment.id).where(Equipment.organization_id == org.id).limit(1)):
            raise RuntimeError("Organization already contains equipment records; refusing to mix synthetic data with existing operations")

        facilities = [Facility(id=stable_id("facility", name), organization_id=org.id,
            name=name, region=region, timezone_name="UTC", active=True)
            for name, region in [("West Assembly", "North"), ("East Processing", "North"),
                                 ("River Pump House", "Central"), ("South Materials", "South")]]
        categories_data = [
            ("Conveyor", "Belt and roller material handling equipment"),
            ("Motor", "AC drive motors and motor assemblies"),
            ("Pump", "Process and utility pumps"),
            ("Compressor", "Plant air and process compressors"),
            ("Crusher", "Primary and secondary material crushers"),
        ]
        categories = [EquipmentCategory(id=stable_id("category", name), organization_id=org.id,
            name=name, description=description) for name, description in categories_data]
        db.add_all(facilities + categories); db.flush()
        facility_by_name = {f.name: f for f in facilities}
        facility_by_id = {f.id: f for f in facilities}
        category_by_name = {c.name: c for c in categories}

        tag_specs = [(f"C-{100+i}", "Conveyor", f"Transfer Conveyor {i+1}") for i in range(18)]
        tag_specs += [(f"M-{100+i}", "Motor", f"Drive Motor {i+1}") for i in range(18)]
        tag_specs += [(f"P-{300+i}", "Pump", f"Process Pump {i+1}") for i in range(16)]
        tag_specs += [(f"A-{400+i}", "Compressor", f"Air Compressor {i+1}") for i in range(14)]
        tag_specs += [(f"CR-{500+i}", "Crusher", f"Primary Crusher {i+1}") for i in range(13)]
        tag_specs.append(("M-204", "Motor", "Conveyor Drive Motor 204"))
        equipment = []
        equipment_by_tag = {}
        for tag, category, name in tag_specs:
            facility = facility_by_name["West Assembly"] if tag == "M-204" else rng.choice(facilities)
            commissioned = as_of_dt - timedelta(days=rng.randint(400, 3200))
            item = Equipment(id=stable_id("equipment", tag), organization_id=org.id,
                facility_id=facility.id, category_id=category_by_name[category].id,
                equipment_tag=tag, name=name, manufacturer=rng.choice(["Northstar Industrial", "Atlas Motion", "Kestrel Works"]),
                model=f"{category[:2].upper()}-{rng.randint(100,999)}", commissioned_at=commissioned,
                criticality="critical" if tag == "M-204" else rng.choice(["high", "medium", "low"]), active=True)
            equipment.append(item); equipment_by_tag[tag] = item
        db.add_all(equipment); db.flush()
        equipment_by_id = {item.id: item for item in equipment}

        technicians = [Technician(id=stable_id("technician", f"tech-{i}"), organization_id=org.id,
            facility_id=rng.choice(facilities).id, display_name=f"Maintenance Technician {i:02d}",
            trade=rng.choice(["Electrical", "Mechanical", "Millwright", "Instrumentation"]), active=True)
            for i in range(1, 33)]
        db.add_all(technicians); db.flush()

        part_specs = [(f"PART-{i:04d}", f"Standard replacement component {i:03d}", round(rng.uniform(18, 1800), 2), rng.randint(1, 45))
                      for i in range(1, 141)]
        part_specs += [("BRG-6205", "Sealed drive-end bearing 6205", 86.50, 6),
                       ("COUP-204", "Flexible motor coupling insert", 214.00, 12),
                       ("SEAL-204", "Motor shaft seal kit", 43.75, 4)]
        parts = [SparePart(id=stable_id("part", part_no), organization_id=org.id,
            part_number=part_no, name=name, description="Synthetic compatible maintenance spare.",
            unit_cost=cost, lead_time_days=lead) for part_no, name, cost, lead in part_specs]
        part_by_number = {p.part_number: p for p in parts}
        db.add_all(parts); db.flush()

        compatibility = []
        for item in equipment:
            selected = rng.sample(parts, 4)
            if item.equipment_tag == "M-204":
                selected = [part_by_number[x] for x in ("BRG-6205", "COUP-204", "SEAL-204")] + selected[:1]
            for part in selected:
                compatibility.append(EquipmentSparePart(organization_id=org.id,
                    equipment_id=item.id, spare_part_id=part.id))
        db.add_all(compatibility)
        inventory = []
        for facility in facilities:
            for part in parts:
                qty = rng.randint(0, 18)
                if facility.name == "West Assembly" and part.part_number == "BRG-6205":
                    qty = 2
                inventory.append(Inventory(id=stable_id("inventory", f"{facility.id}:{part.id}"),
                    organization_id=org.id, facility_id=facility.id, spare_part_id=part.id,
                    quantity_available=qty, reorder_level=5, checked_at=as_of_dt - timedelta(hours=rng.randint(1, 168))))
        db.add_all(inventory); db.flush()

        failures = []
        for i in range(1000):
            item = rng.choice(equipment)
            occurred = as_of_dt - timedelta(days=rng.randint(1, 730), hours=rng.randint(0, 23))
            mode = rng.choice(["bearing wear", "shaft misalignment", "overheating", "seal leakage", "electrical fault"])
            failures.append(FailureEvent(id=stable_id("failure", f"random-{i}"), organization_id=org.id,
                equipment_id=item.id, incident_code=f"INC-SYN-{i:05d}", occurred_at=occurred,
                failure_mode=mode, root_cause=rng.choice(["lubrication breakdown", "dust ingress", "alignment drift", "overload", "component fatigue"]),
                severity=rng.choice(["low", "medium", "high"]), downtime_minutes=rng.randint(20, 560),
                lost_production_units=rng.randint(0, 850),
                resolved_at=occurred + timedelta(minutes=rng.randint(30, 600))))
        m204 = equipment_by_tag["M-204"]
        special_failures = []
        for i, day_offset in enumerate([12, 27, 43, 58, 72, 87], start=1):
            occurred = as_of_dt - timedelta(days=day_offset)
            special_failures.append(FailureEvent(id=stable_id("failure", f"m204-{i}"), organization_id=org.id,
                equipment_id=m204.id, incident_code=f"INC-M204-{i:03d}", occurred_at=occurred,
                failure_mode="drive-end bearing overheating",
                root_cause=("Dust-contaminated grease and elevated vibration" if i % 2
                            else "Coupling alignment remained outside tolerance after prior replacement"),
                severity="high", downtime_minutes=220 + i * 37, lost_production_units=300 + i * 45,
                resolved_at=occurred + timedelta(hours=5, minutes=i * 9)))
        failures.extend(special_failures)
        db.add_all(failures); db.flush()

        work_orders = []
        failure_by_id = {f.id: f for f in failures}
        for i in range(800):
            failure = rng.choice(failures) if rng.random() < .7 else None
            item = equipment_by_id[failure.equipment_id] if failure else rng.choice(equipment)
            created = (failure.occurred_at + timedelta(hours=1)) if failure else as_of_dt - timedelta(days=rng.randint(1, 700))
            status = rng.choice(["open", "in_progress", "completed", "completed", "cancelled"])
            work_orders.append(WorkOrder(id=stable_id("work-order", f"{i}"), organization_id=org.id,
                equipment_id=item.id, failure_event_id=failure.id if failure else None, requested_by=None,
                idempotency_key=f"synthetic-wo-{i:05d}", description=f"Synthetic {rng.choice(['inspection','repair','preventive service'])} for {item.equipment_tag}",
                priority="high" if item.criticality in {"critical", "high"} else "normal", status=status,
                estimated_cost=round(rng.uniform(80, 4200), 2),
                actual_cost=round(rng.uniform(50, 5000), 2) if status == "completed" else None,
                created_at=created, completed_at=created + timedelta(hours=rng.randint(2, 72)) if status == "completed" else None))
        db.add_all(work_orders); db.flush()
        work_order_by_failure = {}
        for order in work_orders:
            if order.failure_event_id:
                work_order_by_failure.setdefault(order.failure_event_id, order)

        maintenance = []
        for i in range(1500):
            failure = rng.choice(failures)
            item = next(e for e in equipment if e.id == failure.equipment_id)
            wo = work_order_by_failure.get(failure.id)
            maintenance.append(MaintenanceLog(id=stable_id("maintenance", str(i)), organization_id=org.id,
                equipment_id=item.id, technician_id=rng.choice(technicians).id, work_order_id=wo.id if wo else None,
                failure_event_id=failure.id, occurred_at=failure.occurred_at + timedelta(hours=rng.randint(1, 72)),
                maintenance_type=rng.choice(["corrective", "preventive", "inspection", "condition-based"]),
                summary=f"Synthetic maintenance record: inspected {failure.failure_mode}; verified operating condition.",
                cost=round(rng.uniform(75, 2400), 2), downtime_minutes=rng.randint(0, 300)))
        for i, failure in enumerate(special_failures):
            wo = work_order_by_failure.get(failure.id)
            maintenance.append(MaintenanceLog(id=stable_id("maintenance", f"m204-{i}"), organization_id=org.id,
                equipment_id=m204.id, technician_id=technicians[i].id, work_order_id=wo.id if wo else None,
                failure_event_id=failure.id, occurred_at=failure.occurred_at + timedelta(hours=5),
                maintenance_type="corrective", summary="Replaced bearing and regreased motor; alignment check recommended at next planned outage.",
                cost=round(620 + i * 35, 2), downtime_minutes=failure.downtime_minutes))
        db.add_all(maintenance)

        metrics = []
        metric_equipment = [m204] + rng.sample([e for e in equipment if e.id != m204.id], 11)
        for item in metric_equipment:
            for day_offset in range(180, -1, -1):
                stamp = as_of_dt - timedelta(days=day_offset)
                failure_risk = 1.0 + (0.7 if item.equipment_tag == "M-204" and day_offset < 90 else 0)
                for name, base, spread, unit in [("vibration_rms", 2.4 * failure_risk, .55, "mm/s"),
                                                  ("bearing_temperature", 62 * failure_risk, 4.5, "C"),
                                                  ("motor_current", 31, 3.2, "A")]:
                    value = max(0, rng.gauss(base, spread))
                    metrics.append(OperationalMetric(id=stable_id("metric", f"{item.id}:{day_offset}:{name}"),
                        organization_id=org.id, equipment_id=item.id, measured_at=stamp,
                        metric_name=name, value=round(value, 3), unit=unit))
        db.add_all(metrics)

        safety = []
        for i in range(90):
            item = m204 if i == 0 else rng.choice(equipment)
            facility = facility_by_id[item.facility_id]
            stamp = as_of_dt - timedelta(days=rng.randint(1, 730))
            safety.append(SafetyIncident(id=stable_id("safety", str(i)), organization_id=org.id,
                facility_id=facility.id, equipment_id=item.id, occurred_at=stamp,
                severity=rng.choice(["near_miss", "minor", "recordable"]),
                summary="Synthetic guard inspection identified a loose fastener during a scheduled walkdown.",
                corrective_action="Isolated equipment, secured guard, and documented verification.",
                lost_time_hours=0 if i % 12 else 2.5))
        db.add_all(safety)
        counts = {"facilities": len(facilities), "categories": len(categories), "equipment": len(equipment),
                  "technicians": len(technicians), "spare_parts": len(parts), "compatibility_links": len(compatibility),
                  "inventory": len(inventory), "failure_events": len(failures), "work_orders": len(work_orders),
                  "maintenance_logs": len(maintenance), "operational_metrics": len(metrics), "safety_incidents": len(safety)}
        manifest = SyntheticDatasetManifest(id=stable_id("manifest", org.id), organization_id=org.id,
            dataset_name=DATASET, generator_version=GENERATOR_VERSION, seed=seed,
            as_of=as_of_dt, record_counts=counts, provenance=PROVENANCE)
        db.add(manifest)
        db.commit()
        return {"status": "generated", "organization_id": org.id, "organization_name": org.name,
                "dataset": DATASET, "as_of": as_of.isoformat(), "counts": counts}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 16))
    args = parser.parse_args()
    print(generate(as_of=args.as_of, seed=args.seed))

if __name__ == "__main__":
    main()
