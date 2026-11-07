
import logging
from datetime import datetime, timezone

from config import settings
from models import (
    ReentryRecord,
    TradingCycle,
)

from binance_client import binance_client
from order_manager import order_manager


logger = logging.getLogger(__name__)


class ReentryManager:

    ACTIVE_STATUSES = [
        "ACTIVE",
        "CLOSING_TP",
        "ORDER_UNCONFIRMED",
    ]

    async def process_waiting(self, db):

        records = (
            db.query(ReentryRecord)
            .filter(
                ReentryRecord.status == "WAITING"
            )
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
                    .filter(
                        TradingCycle.id == record.cycle_id
                    )
                    .first()
                )

                if (
                    not old_cycle
                    or old_cycle.status != "CLOSED"
                ):
                    continue

                # اسی سمت میں پہلے سے فعال Cycle ہو تو انتظار کریں۔
                existing_same_direction = (
                    db.query(TradingCycle)
                    .filter(
                        TradingCycle.symbol == record.symbol,
                        TradingCycle.direction == record.direction,
                        TradingCycle.status.in_(
                            self.ACTIVE_STATUSES
                        ),
                    )
                    .first()
                )

                if existing_same_direction:
                    continue

                # ایک Coin پر مقررہ حد سے زیادہ فعال Cycles نہ ہوں۔
                active_count = (
                    db.query(TradingCycle)
                    .filter(
                        TradingCycle.symbol == record.symbol,
                        TradingCycle.status.in_(
                            self.ACTIVE_STATUSES
                        ),
                    )
                    .count()
                )

                if (
                    active_count
                    >= settings.MAX_ACTIVE_CYCLES_PER_SYMBOL
                ):
                    logger.info(
                        "Re-entry waiting for %s: active cycle limit reached.",
                        record.symbol,
                    )
                    continue

                price = await binance_client.get_market_price(
                    record.symbol
                )

                if not price or price <= 0:
                    continue

                if record.direction == "LONG":

                    reached = (
                        price <= record.trigger_price
                    )

                elif record.direction == "SHORT":

                    reached = (
                        price >= record.trigger_price
                    )

                else:

                    logger.error(
                        "Invalid re-entry direction: %s",
                        record.direction,
                    )
                    continue

                if not reached:
                    continue

                # نئی Cycle موجودہ server configuration استعمال کرے گی۔
                new_cycle = TradingCycle(
                    symbol=record.symbol,
                    direction=record.direction,
                    status="ACTIVE",
                    initial_margin=settings.DEFAULT_INITIAL_MARGIN,
                    averaging_margin=settings.DEFAULT_AVERAGING_MARGIN,
                    opposite_margin=settings.DEFAULT_OPPOSITE_MARGIN,
                    leverage=settings.DEFAULT_LEVERAGE,
                    tp_percent=settings.DEFAULT_TP_PERCENT,
                    sl_percent=settings.DEFAULT_SL_PERCENT,
                    warning_percent=settings.DEFAULT_WARNING_PERCENT,
                    opposite_percent=settings.DEFAULT_OPPOSITE_PERCENT,
                    averaging_percent=settings.DEFAULT_AVERAGING_PERCENT,
                    reentry_percent=settings.DEFAULT_REENTRY_PERCENT,
                )

                db.add(new_cycle)
                db.flush()

                new_cycle_id = new_cycle.id

                # پہلے Re-entry کو PROCESSING محفوظ کریں۔
                saved_record = (
                    db.query(ReentryRecord)
                    .filter(
                        ReentryRecord.id == record_id
                    )
                    .with_for_update()
                    .first()
                )

                if (
                    not saved_record
                    or saved_record.status != "WAITING"
                ):
                    db.rollback()
                    continue

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
                        .filter(
                            ReentryRecord.id == record_id
                        )
                        .first()
                    )

                    saved_cycle = (
                        db.query(TradingCycle)
                        .filter(
                            TradingCycle.id == new_cycle_id
                        )
                        .first()
                    )

                    if (
                        result.get("success")
                        and result.get("order_status") != "UNKNOWN"
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
                        .filter(
                            ReentryRecord.id == record_id
                        )
                        .first()
                    )

                    saved_cycle = (
                        db.query(TradingCycle)
                        .filter(
                            TradingCycle.id == new_cycle_id
                        )
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
