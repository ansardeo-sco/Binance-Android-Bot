
from config import settings
from models import TradingCycle, CycleEvent, CycleOrder, CycleEntry
from automated_entry_manager import automated_entry_manager


OPEN_ORDER_STATUSES = [
    "PENDING",
    "PARTIALLY_FILLED",
    "UNKNOWN",
]

ACTIVE_CYCLE_STATUSES = [
    "ACTIVE",
    "CLOSING_TP",
    "ORDER_UNCONFIRMED",
]


class OppositePositionManager:

    def process_cycle(self, db, cycle, adverse_percent):

        if cycle.status != "ACTIVE":
            return {"triggered": False}

        if cycle.opposite_triggered:
            return {
                "triggered": False,
                "message": "Opposite position already triggered.",
            }

        if adverse_percent < cycle.opposite_percent:
            return {"triggered": False}

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

        opposite_direction = (
            "SHORT" if cycle.direction == "LONG" else "LONG"
        )

        existing = (
            db.query(TradingCycle)
            .filter(
                TradingCycle.symbol == cycle.symbol,
                TradingCycle.direction == opposite_direction,
                TradingCycle.status.in_(ACTIVE_CYCLE_STATUSES),
            )
            .first()
        )

        if existing:
            cycle.opposite_triggered = True
            cycle.opposite_cycle_id = existing.id
            db.commit()

            self._record_event(
                db,
                cycle,
                adverse_percent,
                "OPPOSITE_SKIPPED",
                "SKIPPED",
                "An opposite-direction cycle already exists.",
            )

            return {
                "triggered": False,
                "message": "Opposite cycle already active.",
                "opposite_cycle_id": existing.id,
            }

        # ایک Symbol کے لیے زیادہ سے زیادہ Active Cycles کی حد۔
        active_count = (
            db.query(TradingCycle)
            .filter(
                TradingCycle.symbol == cycle.symbol,
                TradingCycle.status.in_(ACTIVE_CYCLE_STATUSES),
            )
            .count()
        )

        if active_count >= settings.MAX_ACTIVE_CYCLES_PER_SYMBOL:
            cycle.opposite_triggered = True
            db.commit()

            self._record_event(
                db,
                cycle,
                adverse_percent,
                "OPPOSITE_SKIPPED",
                "SKIPPED",
                "Maximum active cycles limit reached for this symbol.",
            )

            return {
                "triggered": False,
                "message": "Maximum active cycles limit reached.",
            }

        # نئی مخالف سمت کی Cycle میں پرانی Cycle کی Settings محفوظ کریں۔
        opposite_cycle = TradingCycle(
            symbol=cycle.symbol,
            direction=opposite_direction,
            status="ACTIVE",
            initial_margin=cycle.opposite_margin,
            averaging_margin=cycle.averaging_margin,
            opposite_margin=cycle.opposite_margin,
            leverage=cycle.leverage,
            tp_percent=cycle.tp_percent,
            sl_percent=cycle.sl_percent,
            warning_percent=cycle.warning_percent,
            opposite_percent=cycle.opposite_percent,
            averaging_percent=cycle.averaging_percent,
            reentry_percent=cycle.reentry_percent,
        )

        db.add(opposite_cycle)
        db.commit()
        db.refresh(opposite_cycle)

        cycle.opposite_triggered = True
        cycle.opposite_cycle_id = opposite_cycle.id
        db.commit()

        try:
            result = automated_entry_manager.place_entry(
                db=db,
                cycle=opposite_cycle,
                entry_type="OPPOSITE",
                margin=cycle.opposite_margin,
            )

            self._record_event(
                db,
                cycle,
                adverse_percent,
                "OPPOSITE_ORDER",
                result.get("status", "SUBMITTED"),
                f"Opposite {opposite_direction} cycle created.",
            )

            return {
                "triggered": True,
                "opposite_cycle_id": opposite_cycle.id,
                "result": result,
            }

        except Exception:
            db.rollback()

            saved_cycle = (
                db.query(TradingCycle)
                .filter(TradingCycle.id == opposite_cycle.id)
                .first()
            )

            if saved_cycle:
                saved_cycle.status = "ORDER_UNCONFIRMED"
                db.commit()

            self._record_event(
                db,
                cycle,
                adverse_percent,
                "OPPOSITE_ORDER",
                "UNKNOWN",
                "Opposite order could not be confirmed. Reconciliation required.",
            )

            return {
                "triggered": False,
                "opposite_cycle_id": opposite_cycle.id,
                "message": "Opposite order status is unknown. Reconciliation required.",
            }

    @staticmethod
    def _record_event(
        db,
        cycle,
        adverse_percent,
        event_type,
        status,
        message,
    ):
        if event_type == "OPPOSITE_SKIPPED":
            key = f"cycle-{cycle.id}-opposite-skipped"
        else:
            key = f"cycle-{cycle.id}-opposite-order"

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
            event_type=event_type,
            price=cycle.average_entry_price,
            percentage=adverse_percent,
            status=status,
            message=message,
            idempotency_key=key,
        )

        db.add(event)
        db.commit()


opposite_position_manager = OppositePositionManager()
