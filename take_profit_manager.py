
from models import CycleEntry, CycleOrder
from close_order_manager import close_order_manager


OPEN_ORDER_STATUSES = [
    "PENDING",
    "PARTIALLY_FILLED",
    "UNKNOWN",
]


class TakeProfitManager:

    def process_cycle(self, db, cycle, current_price: float):

        if cycle.status not in ("ACTIVE", "CLOSING_TP"):
            return {
                "triggered": False,
                "message": "Cycle is not active or closing.",
            }

        # پہلے سے کوئی Close Order زیرِ تصدیق ہو تو انتظار کریں۔
        pending_close = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.reduce_position.is_(True),
                CycleOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .first()
        )

        if pending_close:
            return {
                "triggered": False,
                "message": "A closing order is already pending or uncertain.",
            }

        # کوئی Entry Order زیرِ تصدیق ہو تو TP بند کرنے کا عمل انتظار کرے گا۔
        pending_entry = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.reduce_position.is_(False),
                CycleOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .first()
        )

        if pending_entry:
            return {
                "triggered": False,
                "message": "An entry order is still pending confirmation.",
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
            .order_by(CycleEntry.id.asc())
            .all()
        )

        if not entries:
            return {
                "triggered": False,
                "message": "No open entry quantity.",
            }

        total_quantity = sum(
            float(entry.remaining_quantity or 0)
            for entry in entries
        )

        if total_quantity <= 0:
            return {
                "triggered": False,
                "message": "No open quantity remains.",
            }

        weighted_value = sum(
            float(entry.entry_price)
            * float(entry.remaining_quantity or 0)
            for entry in entries
        )

        average_price = weighted_value / total_quantity

        if average_price <= 0:
            return {
                "triggered": False,
                "message": "Invalid average entry price.",
            }

        if cycle.direction == "LONG":

            profit_percent = (
                (current_price - average_price)
                / average_price
            ) * 100

            target_price = average_price * (
                1 + cycle.tp_percent / 100
            )

        elif cycle.direction == "SHORT":

            profit_percent = (
                (average_price - current_price)
                / average_price
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

        # پہلی مرتبہ TP تک پہنچنے پر سائیکل بند کرنے کا عمل شروع ہوگا۔
        if cycle.status == "ACTIVE":

            if profit_percent < cycle.tp_percent:
                db.commit()

                return {
                    "triggered": False,
                    "profit_percent": profit_percent,
                    "target_price": target_price,
                }

            cycle.status = "CLOSING_TP"
            db.commit()

        # CLOSING_TP میں قیمت واپس آنے کے باوجود باقی Entries بند ہوں گی۔
        # ایک وقت میں صرف ایک Entry کا Close Order بھیجا جائے گا۔
        entry = entries[0]

        result = close_order_manager.close_entry(
            db=db,
            entry_id=entry.id,
            reason="TAKE_PROFIT",
        )

        return {
            "triggered": True,
            "cycle_id": cycle.id,
            "profit_percent": profit_percent,
            "target_price": target_price,
            "closing_result": result,
            "message": (
                "One entry close order submitted. "
                "Remaining entries will be closed after confirmation."
            ),
        }


take_profit_manager = TakeProfitManager()
