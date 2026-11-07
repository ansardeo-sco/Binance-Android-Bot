from models import CycleEntry, CycleOrder, CycleEvent
from automated_entry_manager import automated_entry_manager


OPEN_ORDER_STATUSES = [
    "PENDING",
    "PARTIALLY_FILLED",
    "UNKNOWN",
]


class AveragingManager:

    def process_cycle(self, db, cycle, adverse_percent):

        if cycle.status != "ACTIVE":
            return {"triggered": False}

        if cycle.averaging_triggered:
            return {
                "triggered": False,
                "message": "Averaging already triggered.",
            }

        if adverse_percent < cycle.averaging_percent:
            return {"triggered": False}

        # پہلے سے موجود Averaging ریکارڈ دوبارہ آرڈر لگنے سے روکے گا۔
        existing = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.entry_type == "AVERAGING",
            )
            .first()
        )

        if existing:
            cycle.averaging_triggered = True
            db.commit()

            return {
                "triggered": False,
                "message": "An averaging entry already exists.",
            }

        pending = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .first()
        )

        if pending:
            return {
                "triggered": False,
                "message": "An order is pending or unconfirmed.",
            }

        try:
            result = automated_entry_manager.place_entry(
                db=db,
                cycle=cycle,
                entry_type="AVERAGING",
                margin=cycle.averaging_margin,
            )

            # آرڈر ریکارڈ بننے کے بعد Flag محفوظ کریں۔
            cycle.averaging_triggered = True
            db.commit()

            self._record_event(
                db,
                cycle,
                adverse_percent,
                result.get("status", "SUBMITTED"),
                "Averaging order submitted.",
            )

            return {
                "triggered": True,
                "result": result,
            }

        except Exception as error:
            # اگر آرڈر کا ریکارڈ بن چکا ہے تو دوبارہ آرڈر نہیں لگے گا۔
            db.rollback()

            saved_entry = (
                db.query(CycleEntry)
                .filter(
                    CycleEntry.cycle_id == cycle.id,
                    CycleEntry.entry_type == "AVERAGING",
                )
                .first()
            )

            if saved_entry:
                cycle.averaging_triggered = True
                db.commit()

                self._record_event(
                    db,
                    cycle,
                    adverse_percent,
                    "UNKNOWN",
                    "Averaging order requires exchange reconciliation.",
                )

                return {
                    "triggered": False,
                    "message": "Averaging order status is unknown. Reconciliation required.",
                }

            return {
                "triggered": False,
                "message": f"Averaging was not submitted: {error}",
            }

    @staticmethod
    def _record_event(db, cycle, adverse_percent, status, message):
        key = f"cycle-{cycle.id}-averaging-order"

        existing = (
            db.query(CycleEvent)
            .filter(CycleEvent.idempotency_key == key)
            .first()
        )

        if existing:
            return

        event = CycleEvent(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            event_type="AVERAGING_ORDER",
            price=cycle.average_entry_price,
            percentage=adverse_percent,
            status=status,
            message=message,
            idempotency_key=key,
        )

        db.add(event)
        db.commit()


averaging_manager = AveragingManager()
