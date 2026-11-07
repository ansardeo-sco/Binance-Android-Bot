import logging
from datetime import datetime, timezone

from config import settings
from models import ReentryRecord, TradingCycle

from binance_client import binance_client
from order_manager import order_manager
from settings_manager import settings_manager


logger = logging.getLogger(__name__)


class ReentryManager:

    ACTIVE_STATUSES = [
        "ACTIVE",
        "CLOSING_TP",
        "ORDER_UNCONFIRMED",
    ]

    @staticmethod
    def _direction_enabled(symbol_settings, direction):

        if direction == "LONG":
            return bool(symbol_settings["enabled_long"])

        if direction == "SHORT":
            return bool(symbol_settings["enabled_short"])

        return False

    async def process_waiting(self, db):

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

                # نئی Re-entry کے لیے موجودہ کوائن کی سیٹنگز حاصل کریں۔
                symbol_settings = settings_manager.get_symbol_settings(
                    db,
                    record.symbol,
                )

                # اگر اس سمت کی اجازت بند ہے تو Re-entry انتظار کرے گی۔
                if not self._direction_enabled(
                    symbol_settings,
                    record.direction,
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

                # Re-entry کو پہلے محفوظ طور پر PROCESSING کریں۔
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

                    # نئی Cycle میں موجودہ Settings محفوظ ہوں گی۔
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

                    order_status = result.get("order_status")

                    if (
                        result.get("success")
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

                except Exception:

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

                    if saved_record:
                        saved_record.status = "ORDER_UNCONFIRMED"

                    if saved_cycle:
                        saved_cycle.status = "ORDER_UNCONFIRMED"

                    db.commit()

                    logger.exception(
                        "Re-entry order could not be confirmed."
                    )

                    results.append({
                        "record_id": record_id,
                        "cycle_id": new_cycle_id,
                        "status": "ORDER_UNCONFIRMED",
                    })

            except Exception:

                db.rollback()

                logger.exception(
                    "Re-entry processing failed for record %s",
                    record_id,
                )

        return results


reentry_manager = ReentryManager()
