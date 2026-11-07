from models import CycleEntry, CycleOrder
from close_order_manager import close_order_manager


class TakeProfitManager:

    def process_cycle(self, db, cycle, current_price: float):

        if cycle.status != "ACTIVE":
            return {
                "triggered": False,
                "message": "Cycle is not active.",
            }

        pending_close = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.reduce_position.is_(True),
                CycleOrder.status.in_([
                    "PENDING",
                    "PARTIALLY_FILLED",
                    "UNKNOWN",
                ]),
            )
            .first()
        )

        if pending_close:
            return {
                "triggered": False,
                "message": "A closing order is already pending or uncertain.",
            }

        entries = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.status.in_([
                    "FILLED",
                    "PARTIALLY_FILLED",
                ]),
                CycleEntry.remaining_quantity > 0,
                CycleEntry.entry_price.isnot(None),
            )
            .all()
        )

        total_quantity = sum(
            float(entry.remaining_quantity or 0)
            for entry in entries
        )

        if total_quantity <= 0:
            return {
                "triggered": False,
                "message": "No open entry quantity.",
            }

        weighted_value = sum(
            float(entry.entry_price)
            * float(entry.remaining_quantity or 0)
            for entry in entries
        )

        average_price = weighted_value / total_quantity

        if cycle.direction == "LONG":
            profit_percent = (
                (current_price - average_price) / average_price
            ) * 100

            target_price = average_price * (
                1 + cycle.tp_percent / 100
            )

        elif cycle.direction == "SHORT":
            profit_percent = (
                (average_price - current_price) / average_price
            ) * 100

            target_price = average_price * (
                1 - cycle.tp_percent / 100
            )

        else:
            return {
                "triggered": False,
                "message": "Invalid cycle direction.",
            }

        cycle.average_entry_price = average_price
        cycle.total_filled_quantity = total_quantity
        cycle.take_profit_price = target_price

        if profit_percent < cycle.tp_percent:
            db.commit()

            return {
                "triggered": False,
                "profit_percent": profit_percent,
                "target_price": target_price,
            }

        # Latch the cycle to prevent duplicate TP submissions.
        cycle.status = "CLOSING_TP"
        db.commit()

        results = []

        for entry in entries:
            if float(entry.remaining_quantity or 0) <= 0:
                continue

            result = close_order_manager.close_entry(
                db=db,
                entry_id=entry.id,
                reason="TAKE_PROFIT",
            )

            results.append(result)

        return {
            "triggered": True,
            "cycle_id": cycle.id,
            "profit_percent": profit_percent,
            "target_price": target_price,
            "closing_results": results,
        }


take_profit_manager = TakeProfitManager()
