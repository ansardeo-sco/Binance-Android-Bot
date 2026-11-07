
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

        threshold_key = f"cycle-{cycle.id}-averaging-threshold"
        order_key = f"cycle-{cycle.id}-averaging-order"

        threshold_event = (
            db.query(CycleEvent)
            .filter(CycleEvent.idempotency_key == threshold_key)
            .first()
        )

        threshold_reached = (
            adverse_percent >= float(cycle.averaging_percent)
        )

        # Once reached, the threshold remains recorded even if price recovers.
        if not threshold_reached and not threshold_event:
            return {"triggered": False}

        if not threshold_event:
            threshold_event = CycleEvent(
                cycle_id=cycle.id,
                symbol=cycle.symbol,
                event_type="AVERAGING_THRESHOLD",
                price=cycle.average_entry_price,
                percentage=adverse_percent,
                status="WAITING",
                message="Averaging threshold reached; waiting for open orders to clear.",
                idempotency_key=threshold_key,
            )
            db.add(threshold_event)
            db.commit()

        existing_entry = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.entry_type == "AVERAGING",
            )
            .first()
        )

        if existing_entry:
            cycle.averaging_triggered = True
            threshold_event.status = "ORDER_EXISTS"
            db.commit()

            return {
                "triggered": False,
                "message": "An averaging entry already exists. No duplicate order will be placed.",
            }

        existing_order_event = (
            db.query(CycleEvent)
            .filter(CycleEvent.idempotency_key == order_key)
            .first()
        )

        if existing_order_event:
            cycle.averaging_triggered = True
            db.commit()

            return {
                "triggered": False,
                "message": "An averaging order is already recorded. Reconciliation is required.",
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
                "message": "Averaging threshold is queued until the pending order is confirmed.",
            }

        try:
            result = automated_entry_manager.place_entry(
                db=db,
                cycle=cycle,
                entry_type="AVERAGING",
                margin=cycle.averaging_margin,
            )

            cycle.averaging_triggered = True
            threshold_event.status = "SUBMITTED"
            threshold_event.message = "Averaging order submitted."
            db.commit()

            self._record_order_event(
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
            db.rollback()

            saved_entry = (
                db.query(CycleEntry)
                .filter(
                    CycleEntry.cycle_id == cycle.id,
                    CycleEntry.entry_type == "AVERAGING",
                )
                .first()
            )

            threshold_event = (
                db.query(CycleEvent)
                .filter(CycleEvent.idempotency_key == threshold_key)
                .first()
            )

            if saved_entry:
                cycle.averaging_triggered = True

                if threshold_event:
                    threshold_event.status = "UNKNOWN"
                    threshold_event.message = (
                        "Averaging order exists but its exchange status is uncertain."
                    )

                db.commit()

                self._record_order_event(
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

            if threshold_event:
                threshold_event.status = "ERROR"
                threshold_event.message = str(error)
                db.commit()

            return {
                "triggered": False,
                "message": f"Averaging was not submitted: {error}",
            }

    @staticmethod
    def _record_order_event(db, cycle, adverse_percent, status, message):
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
