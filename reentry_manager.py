
import logging
from datetime import datetime, timezone

from config import settings
from models import (
    ReentryRecord,
    TradingCycle,
    CycleEntry,
    CycleOrder,
)

from binance_client import binance_client
from order_manager import order_manager
from settings_manager import settings_manager


logger = logging.getLogger(__name__)
EPSILON = 0.00000001


class ReentryManager:

    ACTIVE_STATUSES = [
        "ACTIVE",
        "CLOSING_TP",
        "ORDER_UNCONFIRMED",
    ]

    TERMINAL_ORDER_STATUSES = {
        "FILLED",
        "CANCELLED",
        "CANCELLED_PARTIAL",
        "REJECTED",
        "EXPIRED",
    }

    @staticmethod
    def _direction_enabled(symbol_settings, direction):
        if direction == "LONG":
            return bool(symbol_settings["enabled_long"])

        if direction == "SHORT":
            return bool(symbol_settings["enabled_short"])

        return False

    @staticmethod
    def _has_confirmed_entry_fill(entries):
        # Historical fill remains proof of execution even if
        # the position was subsequently closed.
        return any(
            float(entry.filled_quantity or 0) > EPSILON
            for entry in entries
        )

    def _recover_incomplete_records(self, db):

        records = (
            db.query(ReentryRecord)
            .filter(
                ReentryRecord.status.in_([
                    "PROCESSING",
                    "ORDER_UNCONFIRMED",
                ])
            )
            .order_by(ReentryRecord.id.asc())
            .all()
        )

        for record in records:

            if not record.new_cycle_id:
                record.status = "WAITING"
                db.commit()
                continue

            cycle_id = record.new_cycle_id

            orders = (
                db.query(CycleOrder)
                .filter(CycleOrder.cycle_id == cycle_id)
                .all()
            )

            entries = (
                db.query(CycleEntry)
                .filter(CycleEntry.cycle_id == cycle_id)
                .all()
            )

            cycle = (
                db.query(TradingCycle)
                .filter(TradingCycle.id == cycle_id)
                .first()
            )

            # No order and no entry: no exchange request was recorded.
            # Safe to retry.
            if not orders and not entries:

                if cycle:
                    cycle.status = "ENTRY_FAILED"

                record.status = "WAITING"
                record.new_cycle_id = None

                db.commit()
                continue

            entries_by_id = {
                entry.id: entry for entry in entries
            }

            # Missing entry/order relationship means the ledger
            # is inconsistent. Never send another order automatically.
            inconsistent = any(
                order.entry_id is None
                or order.entry_id not in entries_by_id
                for order in orders
            ) or (bool(entries) and not orders)

            if inconsistent or not orders:

                record.status = "ORDER_UNCONFIRMED"

                if cycle:
                    cycle.status = "ORDER_UNCONFIRMED"

                db.commit()
                continue

            # Open, partially-filled or UNKNOWN orders must be
            # reconciled before any retry.
            unresolved = any(
                str(order.status or "").upper()
                not in self.TERMINAL_ORDER_STATUSES
                for order in orders
            )

            if unresolved:

                record.status = "ORDER_UNCONFIRMED"

                if cycle:
                    cycle.status = "ORDER_UNCONFIRMED"

                db.commit()
                continue

            has_order_fill = any(
                float(order.filled_quantity or 0) > EPSILON
                for order in orders
            )

            has_entry_fill = self._has_confirmed_entry_fill(entries)

            # A confirmed fill means the re-entry was genuinely opened.
            if has_order_fill and has_entry_fill:

                record.status = "TRIGGERED"

                if not record.triggered_at:
                    record.triggered_at = datetime.now(timezone.utc)

                db.commit()
                continue

            # Exchange and local ledger disagree about execution.
            # Keep it locked for reconciliation.
            if has_order_fill != has_entry_fill:

                record.status = "ORDER_UNCONFIRMED"

                if cycle:
                    cycle.status = "ORDER_UNCONFIRMED"

                db.commit()
                continue

            # Every order is terminal and zero-fill.
            # It is now safe to retry this same re-entry record.
            if cycle:
                cycle.status = "ENTRY_FAILED"

            record.status = "WAITING"
            record.new_cycle_id = None

            db.commit()

    async def process_waiting(self, db):

        self._recover_incomplete_records(db)

        records = (
            db.query(ReentryRecord)
            .filter(ReentryRecord.status == "WAITING")
            .order_by(ReentryRecord.id.asc())
            .all()
        )

        results = []

        for record in records:

            record_id = record.id
            new_cycle_id = None

            try:

                old_cycle = (
                    db.query(TradingCycle)
                    .filter(TradingCycle.id == record.cycle_id)
                    .first()
                )

                if not old_cycle or old_cycle.status != "CLOSED":
                    continue

                existing_same_direction = (
                    db.query(TradingCycle)
                    .filter(
                        TradingCycle.symbol == record.symbol,
                        TradingCycle.direction == record.direction,
                        TradingCycle.status.in_(self.ACTIVE_STATUSES),
                    )
                    .first()
                )

                if existing_same_direction:
                    continue

                active_count = (
                    db.query(TradingCycle)
                    .filter(
                        TradingCycle.symbol == record.symbol,
                        TradingCycle.status.in_(self.ACTIVE_STATUSES),
                    )
                    .count()
                )

                if active_count >= settings.MAX_ACTIVE_CYCLES_PER_SYMBOL:
                    continue

                symbol_settings = settings_manager.get_symbol_settings(
                    db, record.symbol
                )

                if not self._direction_enabled(
                    symbol_settings, record.direction
                ):
                    continue

                price = await binance_client.get_market_price(
                    record.symbol
                )

                if not price or price <= 0:
                    continue

                if record.direction == "LONG":
                    reached = price <= record.trigger_price

                elif record.direction == "SHORT":
                    reached = price >= record.trigger_price

                else:
                    logger.error(
                        "Invalid re-entry direction: %s",
                        record.direction,
                    )
                    continue

                if not reached:
                    continue

                saved_record = (
                    db.query(ReentryRecord)
                    .filter(ReentryRecord.id == record_id)
                    .with_for_update()
                    .first()
                )

                if not saved_record or saved_record.status != "WAITING":
                    db.rollback()
                    continue

                new_cycle = TradingCycle(
                    symbol=record.symbol,
                    direction=record.direction,
                    status="ACTIVE",
                    initial_margin=symbol_settings["initial_margin"],
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

                db.add(new_cycle)
                db.flush()

                new_cycle_id = new_cycle.id

                saved_record.status = "PROCESSING"
                saved_record.new_cycle_id = new_cycle_id

                db.commit()

                try:

                    result = order_manager.place_initial_entry(
                        db,
                        new_cycle,
                    )

                    saved_record = (
                        db.query(ReentryRecord)
                        .filter(ReentryRecord.id == record_id)
                        .first()
                    )

                    saved_cycle = (
                        db.query(TradingCycle)
                        .filter(TradingCycle.id == new_cycle_id)
                        .first()
                    )

                    filled_quantity = float(
                        (result or {}).get("filled_quantity") or 0
                    )

                    order_status = str(
                        (result or {}).get("order_status") or "UNKNOWN"
                    ).upper()

                    # Only a confirmed non-zero fill consumes re-entry.
                    if (
                        (result or {}).get("success")
                        and filled_quantity > EPSILON
                        and order_status != "UNKNOWN"
                    ):

                        if saved_record:
                            saved_record.status = "TRIGGERED"
                            saved_record.triggered_at = (
                                datetime.now(timezone.utc)
                            )

                        db.commit()

                        results.append({
                            "record_id": record_id,
                            "cycle_id": new_cycle_id,
                            "status": "TRIGGERED",
                            "order": result,
                        })

                    else:

                        if saved_cycle:
                            saved_cycle.status = "ORDER_UNCONFIRMED"

                        if saved_record:
                            saved_record.status = "ORDER_UNCONFIRMED"

                        db.commit()

                        results.append({
                            "record_id": record_id,
                            "cycle_id": new_cycle_id,
                            "status": "ORDER_UNCONFIRMED",
                        })

                except Exception as error:

                    db.rollback()

                    saved_record = (
                        db.query(ReentryRecord)
                        .filter(ReentryRecord.id == record_id)
                        .first()
                    )

                    saved_cycle = (
                        db.query(TradingCycle)
                        .filter(TradingCycle.id == new_cycle_id)
                        .first()
                    )

                    saved_order = (
                        db.query(CycleOrder)
                        .filter(
                            CycleOrder.cycle_id == new_cycle_id
                        )
                        .first()
                    )

                    saved_entry = (
                        db.query(CycleEntry)
                        .filter(
                            CycleEntry.cycle_id == new_cycle_id
                        )
                        .first()
                    )

                    exchange_request_may_exist = bool(
                        saved_order or saved_entry
                    )

                    if saved_record:

                        if exchange_request_may_exist:
                            saved_record.status = "ORDER_UNCONFIRMED"

                        else:
                            saved_record.status = "WAITING"
                            saved_record.new_cycle_id = None

                    if saved_cycle:

                        saved_cycle.status = (
                            "ORDER_UNCONFIRMED"
                            if exchange_request_may_exist
                            else "ENTRY_FAILED"
                        )

                    db.commit()

                    logger.exception(
                        "Re-entry order could not be confirmed: %s",
                        error,
                    )

                    results.append({
                        "record_id": record_id,
                        "cycle_id": new_cycle_id,
                        "status": (
                            "ORDER_UNCONFIRMED"
                            if exchange_request_may_exist
                            else "WAITING_RETRY"
                        ),
                    })

            except Exception:

                db.rollback()

                logger.exception(
                    "Re-entry processing failed for record %s",
                    record_id,
                )

        return results


reentry_manager = ReentryManager()
