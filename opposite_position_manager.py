from models import TradingCycle, CycleEvent, CycleOrder
from automated_entry_manager import automated_entry_manager


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

        opposite_direction = (
            "SHORT" if cycle.direction == "LONG" else "LONG"
        )

        existing = (
            db.query(TradingCycle)
            .filter(
                TradingCycle.symbol == cycle.symbol,
                TradingCycle.direction == opposite_direction,
                TradingCycle.status.in_([
                    "ACTIVE",
                    "CLOSING_TP",
                    "ORDER_UNCONFIRMED",
                ]),
            )
            .first()
        )

        if existing:
            cycle.opposite_triggered = True
            cycle.opposite_cycle_id = existing.id
            db.commit()

            event = CycleEvent(
                cycle_id=cycle.id,
                symbol=cycle.symbol,
                event_type="OPPOSITE_SKIPPED",
                price=cycle.average_entry_price,
                percentage=adverse_percent,
                status="SKIPPED",
                message="An opposite-direction cycle already exists.",
                idempotency_key=f"cycle-{cycle.id}-opposite-skipped",
            )

            db.add(event)
            db.commit()

            return {
                "triggered": False,
                "message": "Opposite cycle already active.",
                "opposite_cycle_id": existing.id,
            }

        # نئے Cycle میں موجودہ Cycle کی Settings کی نقل۔
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

        # اصل Cycle میں بھی ریکارڈ محفوظ کریں۔
        cycle.opposite_triggered = True
        cycle.opposite_cycle_id = opposite_cycle.id
        db.commit()

        result = automated_entry_manager.place_entry(
            db=db,
            cycle=opposite_cycle,
            entry_type="OPPOSITE",
            margin=cycle.opposite_margin,
        )

        event = CycleEvent(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            event_type="OPPOSITE_ORDER",
            price=cycle.average_entry_price,
            percentage=adverse_percent,
            status=result["status"],
            message=(
                f"Opposite {opposite_direction} cycle created."
            ),
            idempotency_key=f"cycle-{cycle.id}-opposite-order",
        )

        db.add(event)
        db.commit()

        return {
            "triggered": True,
            "opposite_cycle_id": opposite_cycle.id,
            "result": result,
        }


opposite_position_manager = OppositePositionManager()
