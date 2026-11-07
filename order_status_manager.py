import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import CycleOrder, CycleEntry, TradingCycle


logger = logging.getLogger(__name__)


class OrderStatusManager:

    TERMINAL_STATUSES = {
        "closed",
        "canceled",
        "cancelled",
        "expired",
        "rejected",
    }

    def sync_pending_orders(self):
        db = SessionLocal()
        results = []

        try:
            orders = (
                db.query(CycleOrder)
                .filter(
                    CycleOrder.status.in_([
                        "PENDING",
                        "PARTIALLY_FILLED",
                    ]),
                    CycleOrder.exchange_order_id.isnot(None),
                )
                .all()
            )

            for order in orders:
                try:
                    exchange_order = (
                        binance_fetch_order(order)
                    )

                    if not exchange_order:
                        continue

                    old_filled = float(
                        order.filled_quantity or 0
                    )

                    new_filled = float(
                        exchange_order.get("filled") or 0
                    )

                    fill_delta = max(
                        0.0,
                        new_filled - old_filled,
                    )

                    average = exchange_order.get("average")

                    exchange_status = str(
                        exchange_order.get("status") or "open"
                    ).lower()

                    entry = None

                    if order.entry_id:
                        entry = (
                            db.query(CycleEntry)
                            .filter(
                                CycleEntry.id == order.entry_id
                            )
                            .first()
                        )

                    order.filled_quantity = new_filled

                    if average is not None:
                        order.average_fill_price = float(average)

                    if entry and fill_delta > 0:

                        if order.reduce_position:
                            entry.remaining_quantity = max(
                                0.0,
                                float(entry.remaining_quantity or 0)
                                - fill_delta,
                            )

                            if entry.remaining_quantity <= 0.00000001:
                                entry.remaining_quantity = 0.0
                                entry.status = "CLOSED"
                                entry.closed_at = datetime.now(
                                    timezone.utc
                                )

                        else:
                            entry.filled_quantity = new_filled

                            entry.remaining_quantity = (
                                float(entry.remaining_quantity or 0)
                                + fill_delta
                            )

                            if average is not None:
                                entry.entry_price = float(average)

                            if not entry.filled_at:
                                entry.filled_at = datetime.now(
                                    timezone.utc
                                )

                    if exchange_status == "closed":
                        order.status = (
                            "FILLED" if new_filled > 0 else "CANCELLED"
                        )

                    elif exchange_status in self.TERMINAL_STATUSES:
                        order.status = (
                            "PARTIALLY_FILLED"
                            if new_filled > 0
                            else "CANCELLED"
                        )

                    elif new_filled > 0:
                        order.status = "PARTIALLY_FILLED"

                    else:
                        order.status = "PENDING"

                    if entry and not order.reduce_position:
                        if exchange_status == "closed" and new_filled > 0:
                            entry.status = "FILLED"
                        elif new_filled > 0:
                            entry.status = "PARTIALLY_FILLED"
                        elif exchange_status in self.TERMINAL_STATUSES:
                            entry.status = "CANCELLED"

                    if order.reduce_position and entry:
                        if entry.remaining_quantity <= 0.00000001:
                            entry.remaining_quantity = 0.0
                            entry.status = "CLOSED"
                            entry.closed_at = datetime.now(timezone.utc)

                    results.append({
                        "order_id": order.id,
                        "exchange_order_id": order.exchange_order_id,
                        "status": order.status,
                        "filled_quantity": new_filled,
                        "new_fill_quantity": fill_delta,
                        "remaining_quantity": (
                            entry.remaining_quantity if entry else None
                        ),
                    })

                    if entry:
                        self._update_cycle_status(
                            db,
                            entry.cycle_id,
                        )

                except Exception:
                    logger.exception(
                        "Unable to synchronize order %s",
                        order.id,
                    )

            db.commit()

            return results

        except Exception:
            db.rollback()
            logger.exception("Order synchronization failed.")
            raise

        finally:
            db.close()

    @staticmethod
    def _update_cycle_status(db, cycle_id):

        cycle = (
            db.query(TradingCycle)
            .filter(TradingCycle.id == cycle_id)
            .first()
        )

        if not cycle:
            return

        entries = (
            db.query(CycleEntry)
            .filter(CycleEntry.cycle_id == cycle_id)
            .all()
        )

        if not entries:
            return

        all_closed = all(
            float(entry.remaining_quantity or 0) <= 0.00000001
            for entry in entries
        )

        if all_closed:
            cycle.status = "CLOSED"

            if not cycle.closed_at:
                cycle.closed_at = datetime.now(timezone.utc)

            return

        pending_closes = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle_id,
                CycleOrder.reduce_position.is_(True),
                CycleOrder.status.in_([
                    "PENDING",
                    "PARTIALLY_FILLED",
                ]),
            )
            .count()
        )

        if pending_closes == 0 and cycle.status == "CLOSING_TP":
            cycle.status = "ACTIVE"


def binance_fetch_order(order):
    from binance_client import binance_client

    return binance_client.exchange.fetch_order(
        order.exchange_order_id,
        order.symbol,
    )


order_status_manager = OrderStatusManager()
