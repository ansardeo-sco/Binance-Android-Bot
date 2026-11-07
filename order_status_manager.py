
import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import (
    CycleOrder,
    CycleEntry,
    TradingCycle,
    ReentryRecord,
)

logger = logging.getLogger(__name__)

EPSILON = 0.00000001

OPEN_ORDER_STATUSES = [
    "PENDING",
    "PARTIALLY_FILLED",
    "UNKNOWN",
]


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
            order_ids = [
                row[0]
                for row in (
                    db.query(CycleOrder.id)
                    .filter(
                        CycleOrder.status.in_(OPEN_ORDER_STATUSES)
                    )
                    .order_by(CycleOrder.id.asc())
                    .all()
                )
            ]

            for local_order_id in order_ids:

                try:
                    order = (
                        db.query(CycleOrder)
                        .filter(CycleOrder.id == local_order_id)
                        .first()
                    )

                    if not order:
                        continue

                    exchange_order = binance_fetch_order(order)

                    if not exchange_order:
                        continue

                    old_filled = float(order.filled_quantity or 0)
                    new_filled = float(exchange_order.get("filled") or 0)

                    # Exchange cumulative fill must never move backwards.
                    new_filled = max(old_filled, new_filled)
                    fill_delta = max(0.0, new_filled - old_filled)

                    average = exchange_order.get("average")
                    exchange_status = str(
                        exchange_order.get("status") or "open"
                    ).lower()

                    entry = None

                    if order.entry_id:
                        entry = (
                            db.query(CycleEntry)
                            .filter(CycleEntry.id == order.entry_id)
                            .first()
                        )

                    exchange_id = exchange_order.get("id")

                    if exchange_id:
                        order.exchange_order_id = str(exchange_id)

                        if entry:
                            entry.exchange_order_id = str(exchange_id)

                    order.filled_quantity = new_filled

                    if average is not None:
                        order.average_fill_price = float(average)

                    if entry and fill_delta > 0:

                        if order.reduce_position:
                            entry.remaining_quantity = max(
                                0.0,
                                float(entry.remaining_quantity or 0) - fill_delta,
                            )

                        else:
                            entry.filled_quantity = new_filled
                            entry.remaining_quantity = (
                                float(entry.remaining_quantity or 0) + fill_delta
                            )

                            if average is not None:
                                entry.entry_price = float(average)

                            if not entry.filled_at:
                                entry.filled_at = datetime.now(timezone.utc)

                    requested = float(order.requested_quantity or 0)

                    is_fully_filled = (
                        requested > 0
                        and new_filled + EPSILON >= requested
                    )

                    if exchange_status == "closed":
                        if is_fully_filled:
                            order.status = "FILLED"
                        elif new_filled > 0:
                            order.status = "CANCELLED_PARTIAL"
                        else:
                            order.status = "CANCELLED"

                    elif exchange_status in self.TERMINAL_STATUSES:
                        order.status = (
                            "CANCELLED_PARTIAL"
                            if new_filled > 0
                            else "CANCELLED"
                        )

                    elif new_filled > 0:
                        order.status = "PARTIALLY_FILLED"

                    else:
                        order.status = "PENDING"

                    if entry:

                        if order.reduce_position:

                            if float(entry.remaining_quantity or 0) <= EPSILON:
                                entry.remaining_quantity = 0.0
                                entry.status = "CLOSED"
                                entry.closed_at = datetime.now(timezone.utc)
                            else:
                                entry.status = "PARTIALLY_FILLED"

                        else:

                            if order.status == "FILLED":
                                entry.status = "FILLED"

                            elif order.status == "CANCELLED":
                                entry.status = "CANCELLED"

                            elif new_filled > 0:
                                entry.status = "PARTIALLY_FILLED"

                            else:
                                entry.status = "PENDING"

                    self._update_cycle_status(db, order.cycle_id)

                    result_item = {
                        "local_order_id": order.id,
                        "exchange_order_id": order.exchange_order_id,
                        "client_order_id": order.client_order_id,
                        "status": order.status,
                        "filled_quantity": new_filled,
                        "new_fill_quantity": fill_delta,
                        "remaining_quantity": (
                            entry.remaining_quantity if entry else None
                        ),
                    }

                    # Commit each order separately. A later failure cannot
                    # roll back earlier successfully synchronized orders.
                    db.commit()
                    results.append(result_item)

                except Exception as error:
                    db.rollback()

                    logger.exception(
                        "Order %s synchronization failed: %s",
                        local_order_id,
                        error,
                    )
                    continue

            return results

        except Exception:
            db.rollback()
            logger.exception("Order synchronization failed.")
            raise

        finally:
            db.close()

    @staticmethod
    def _create_tp_reentry(db, cycle):

        existing = (
            db.query(ReentryRecord)
            .filter(ReentryRecord.cycle_id == cycle.id)
            .first()
        )

        if existing:
            return

        tp_orders = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle.id,
                CycleOrder.reduce_position.is_(True),
                CycleOrder.order_type == "TAKE_PROFIT_CLOSE",
                CycleOrder.filled_quantity > 0,
            )
            .all()
        )

        total_quantity = 0.0
        total_value = 0.0

        for order in tp_orders:
            quantity = float(order.filled_quantity or 0)
            price = float(order.average_fill_price or 0)

            if quantity <= 0 or price <= 0:
                continue

            total_quantity += quantity
            total_value += quantity * price

        if total_quantity <= EPSILON:
            logger.warning(
                "No confirmed TP close fills for cycle %s. Re-entry not created.",
                cycle.id,
            )
            return

        reference_price = total_value / total_quantity
        reentry_percent = float(cycle.reentry_percent or 0)

        if reentry_percent <= 0:
            logger.warning(
                "Invalid re-entry percentage for cycle %s.",
                cycle.id,
            )
            return

        if cycle.direction == "LONG":
            trigger_price = reference_price * (
                1 - reentry_percent / 100
            )

        elif cycle.direction == "SHORT":
            trigger_price = reference_price * (
                1 + reentry_percent / 100
            )

        else:
            logger.error(
                "Invalid cycle direction for re-entry: %s",
                cycle.direction,
            )
            return

        record = ReentryRecord(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            direction=cycle.direction,
            reference_close_price=reference_price,
            trigger_price=trigger_price,
            status="WAITING",
        )

        cycle.reentry_price = trigger_price
        db.add(record)

        logger.info(
            "Re-entry created for cycle %s: %s at %s",
            cycle.id,
            cycle.direction,
            trigger_price,
        )

    @classmethod
    def _update_cycle_status(cls, db, cycle_id):

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

        unresolved_orders = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle_id,
                CycleOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .count()
        )

        # PARTIALLY_FILLED entries can be valid open positions. They must
        # not prevent a cycle from returning to ACTIVE after a close order
        # has reached a terminal state.
        unresolved_entries = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle_id,
                CycleEntry.status.in_([
                    "PENDING",
                    "UNKNOWN",
                ]),
            )
            .count()
        )

        all_entries_closed = all(
            float(entry.remaining_quantity or 0) <= EPSILON
            for entry in entries
        )

        if (
            all_entries_closed
            and unresolved_orders == 0
            and unresolved_entries == 0
        ):
            was_closing_tp = cycle.status == "CLOSING_TP"

            cycle.status = "CLOSED"

            if not cycle.closed_at:
                cycle.closed_at = datetime.now(timezone.utc)

            if was_closing_tp:
                cls._create_tp_reentry(db, cycle)

            return

        pending_closes = (
            db.query(CycleOrder)
            .filter(
                CycleOrder.cycle_id == cycle_id,
                CycleOrder.reduce_position.is_(True),
                CycleOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .count()
        )

        if (
            pending_closes == 0
            and cycle.status in (
                "CLOSING_TP",
                "ORDER_UNCONFIRMED",
            )
            and unresolved_orders == 0
            and unresolved_entries == 0
        ):
            cycle.status = "ACTIVE"
            cycle.closed_at = None


def binance_fetch_order(order):

    from binance_client import binance_client

    exchange = binance_client.exchange

    if order.exchange_order_id:
        return exchange.fetch_order(
            order.exchange_order_id,
            order.symbol,
        )

    if order.client_order_id:
        return exchange.fetch_order(
            None,
            order.symbol,
            {
                "origClientOrderId": order.client_order_id
            },
        )

    raise RuntimeError(
        "Order has neither exchange ID nor client order ID."
    )


order_status_manager = OrderStatusManager()
