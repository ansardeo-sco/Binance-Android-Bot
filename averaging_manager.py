from models import CycleEntry, CycleOrder, CycleEvent
from automated_entry_manager import automated_entry_manager


class AveragingManager:

    def process_cycle(self, db, cycle, adverse_percent):

        if cycle.status != "ACTIVE":
            return {"triggered": False}

        if cycle.averaging_triggered:
            return {"triggered": False, "message": "Already averaged."}

        if adverse_percent < cycle.averaging_percent:
            return {"triggered": False}

        pending = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.status.in_([
                    "PENDING",
                    "PARTIALLY_FILLED",
                    "UNKNOWN",
                ]),
            )
            .first()
        )

        if pending:
            return {
                "triggered": False,
                "message": "An order is pending or unconfirmed.",
            }

        existing = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.entry_type == "AVERAGING",
                CycleEntry.status.in_([
                    "PENDING",
                    "PARTIALLY_FILLED",
                    "FILLED",
                    "UNKNOWN",
                ]),
            )
            .first()
        )

        if existing:
            cycle.averaging_triggered = True
            db.commit()

            return {
                "triggered": False,
                "message": "Averaging entry already exists.",
            }

        # پہلے Flag محفوظ کریں تاکہ دوبارہ آرڈر نہ لگے۔
        cycle.averaging_triggered = True
        db.commit()

        result = automated_entry_manager.place_entry(
            db=db,
            cycle=cycle,
            entry_type="AVERAGING",
            margin=cycle.averaging_margin,
        )

        event = CycleEvent(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            event_type="AVERAGING_ORDER",
            price=cycle.average_entry_price,
            percentage=adverse_percent,
            status=result["status"],
            message="Averaging order submitted.",
            idempotency_key=f"cycle-{cycle.id}-averaging-order",
        )

        db.add(event)
        db.commit()

        return {
            "triggered": True,
            "result": result,
        }


averaging_manager = AveragingManager()
