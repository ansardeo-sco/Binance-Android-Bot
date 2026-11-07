from config import settings
from models import TradingCycle, CycleEvent, CycleOrder
from automated_entry_manager import automated_entry_manager
from settings_manager import settings_manager


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

    @staticmethod
    def _direction_enabled(symbol_settings, direction):

        if direction == "LONG":
            return bool(symbol_settings["enabled_long"])

        if direction == "SHORT":
            return bool(symbol_settings["enabled_short"])

        return False

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

        # موجودہ کوائن کی تازہ Settings حاصل کریں۔
        symbol_settings = settings_manager.get_symbol_settings(
            db,
            cycle.symbol,
        )

        # جس سمت کی اجازت بند ہو، اس میں انٹری نہیں ہوگی۔
        if not self._direction_enabled(
            symbol_settings,
            opposite_direction,
        ):

            cycle.opposite_triggered = True
            db.commit()

            self._record_event(
                db,
                cycle,
                adverse_percent,
                "OPPOSITE_SKIPPED",
                "SKIPPED",
                (
                    f"{opposite_direction} trading is disabled "
                    "in the current symbol settings."
                ),
            )

            return {
                "triggered": False,
                "message": (
                    f"{opposite_direction} trading is disabled."
                ),
            }

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

        # نئی Cycle میں موجودہ کوائن کی Settings محفوظ کریں۔
        opposite_cycle = TradingCycle(
            symbol=cycle.symbol,
            direction=opposite_direction,
            status="ACTIVE",

            # مخالف سمت کی پہلی انٹری Opposite Margin سے ہوگی۔
            initial_margin=symbol_settings["opposite_margin"],
            averaging_margin=symbol_settings["averaging_margin"],
            opposite_margin=symbol_settings["opposite_margin"],

            leverage=symbol_settings["leverage"],

            tp_percent=symbol_settings["tp_percent"],
            sl_percent=symbol_settings["sl_percent"],

            warning_percent=symbol_settings["warning_percent"],
            opposite_percent=symbol_settings["opposite_percent"],
            averaging_percent=symbol_settings["averaging_percent"],
            reentry_percent=symbol_settings["reentry_percent"],
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
                margin=opposite_cycle.initial_margin,
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
                (
                    "Opposite order could not be confirmed. "
                    "Reconciliation required."
                ),
            )

            return {
                "triggered": False,
                "opposite_cycle_id": opposite_cycle.id,
                "message": (
                    "Opposite order status is unknown. "
                    "Reconciliation required."
                ),
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
