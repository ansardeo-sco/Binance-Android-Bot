import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import CycleOrder, CycleEntry


logger = logging.getLogger(__name__)


class OrderStatusManager:

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
                    ])
                )
                .all()
            )

            for order in orders:
                if not order.exchange_order_id:
                    continue

                try:
                    exchange_order = (
                        self._fetch_exchange_order(order)
                    )

                    if not exchange_order:
                        continue

                    filled = float(
                        exchange_order.get("filled") or 0
                    )

                    average = exchange_order.get("average")
                    status = str(
                        exchange_order.get("status") or "open"
                    ).lower()

                    order.filled_quantity = filled

                    if average:
                        order.average_fill_price = float(average)

                    entry = None

                    if order.entry_id:
                        entry = (
                            db.query(CycleEntry)
                            .filter(
                                CycleEntry.id == order.entry_id
                            )
                            .first()
                        )

                    if entry:
                        entry.filled_quantity = filled
                        entry.remaining_quantity = max(
                            0.0,
                            filled - (
                                entry.filled_quantity - filled
                            ),
                        )

                        if average:
                            entry.entry_price = float(average)

                        if filled > 0 and not entry.filled_at:
                            entry.filled_at = datetime.now(
                                timezone.utc
                            )

                        if status == "closed":
                            entry.status = (
                                "FILLED" if filled > 0 else "CANCELLED"
                            )

                        elif status in (
                            "canceled",
                            "cancelled",
                            "expired",
                            "rejected",
                        ):
                            entry.status = (
                                "PARTIALLY_FILLED"
                                if filled > 0
                                else "CANCELLED"
                            )

                        elif filled > 0:
                            entry.status = "PARTIALLY_FILLED"

                    if status == "closed":
                        order.status = (
                            "FILLED" if filled > 0 else "CANCELLED"
                        )

                    elif status in (
                        "canceled",
                        "cancelled",
                        "expired",
                        "rejected",
                    ):
                        order.status = (
                            "PARTIALLY_FILLED"
                            if filled > 0
                            else "CANCELLED"
                        )

                    elif filled > 0:
                        order.status = "PARTIALLY_FILLED"

                    results.append({
                        "order_id": order.id,
                        "exchange_order_id": order.exchange_order_id,
                        "status": order.status,
                        "filled_quantity": filled,
                    })

                except Exception:
                    logger.exception(
                        "Unable to synchronize order %s",
                        order.id,
                    )

            db.commit()

            return results

        except Exception:
            db.rollback()
            logger.exception("Order synchronization failed")
            raise

        finally:
            db.close()

    @staticmethod
    def _fetch_exchange_order(order):
        from binance_client import binance_client

        return binance_client.exchange.fetch_order(
            order.exchange_order_id,
            order.symbol,
        )


order_status_manager = OrderStatusManager()
