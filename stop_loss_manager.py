from models import CycleEntry
from close_order_manager import close_order_manager


class StopLossManager:

    def process_cycle(self, db, cycle, current_price: float):

        if cycle.status != "ACTIVE":
            return {
                "processed": False,
                "message": "Cycle is not active.",
            }

        if current_price is None or float(current_price) <= 0:
            return {
                "processed": False,
                "message": "Invalid market price.",
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
            )
            .all()
        )

        results = []

        for entry in entries:

            if not entry.entry_price:
                continue

            entry_price = float(entry.entry_price)
            stop_percent = float(entry.stop_loss_percent or 0)

            if stop_percent <= 0:
                continue

            direction = str(
                entry.direction or cycle.direction
            ).upper()

            if direction == "LONG":

                loss_percent = (
                    (entry_price - current_price)
                    / entry_price
                ) * 100

                stop_price = entry_price * (
                    1 - stop_percent / 100
                )

            elif direction == "SHORT":

                loss_percent = (
                    (current_price - entry_price)
                    / entry_price
                ) * 100

                stop_price = entry_price * (
                    1 + stop_percent / 100
                )

            else:
                continue

            entry.stop_loss_price = stop_price

            if loss_percent < stop_percent:
                continue

            result = close_order_manager.close_entry(
                db=db,
                entry_id=entry.id,
                reason="STOP_LOSS",
            )

            results.append({
                "entry_id": entry.id,
                "direction": direction,
                "loss_percent": loss_percent,
                "stop_loss_percent": stop_percent,
                "stop_loss_price": stop_price,
                "closing_result": result,
            })

        db.commit()

        return {
            "processed": True,
            "cycle_id": cycle.id,
            "triggered_entries": len(results),
            "results": results,
        }


stop_loss_manager = StopLossManager()
