import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal

from models import (
    TradingCycle,
    CycleEntry,
    CycleEvent,
    CycleOrder,
)

from binance_client import binance_client
from order_status_manager import order_status_manager
from take_profit_manager import take_profit_manager
from stop_loss_manager import stop_loss_manager

from averaging_manager import averaging_manager
from opposite_position_manager import opposite_position_manager


logger = logging.getLogger(__name__)


class TradingEngine:

    def __init__(self):
        self.running = False
        self._lock = asyncio.Lock()

    async def start(self):

        if self.running:
            return

        self.running = True
        logger.info("Trading engine started.")

        while self.running:

            try:
                await self.process_active_cycles()

            except Exception:
                logger.exception("Trading engine processing error.")

            await asyncio.sleep(settings.MARKET_POLL_INTERVAL)

    def stop(self):
        self.running = False
        logger.info("Trading engine stopped.")

    async def process_active_cycles(self):

        async with self._lock:

            try:
                order_status_manager.sync_pending_orders()

            except Exception:
                logger.exception(
                    "Pending order synchronization failed."
                )

            db = SessionLocal()

            try:

                cycles = (
                    db.query(TradingCycle)
                    .filter(TradingCycle.status == "ACTIVE")
                    .all()
                )

                for cycle in cycles:

                    try:
                        await self.process_cycle(db, cycle)

                    except Exception:

                        db.rollback()

                        logger.exception(
                            "Cycle processing failed: %s",
                            cycle.id,
                        )

            finally:
                db.close()

    async def process_cycle(self, db: Session, cycle: TradingCycle):

        price = await binance_client.get_market_price(
            cycle.symbol
        )

        if price <= 0:
            return

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

        if not entries:
            return

        total_quantity = sum(
            float(entry.remaining_quantity or 0)
            for entry in entries
        )

        if total_quantity <= 0:
            return

        weighted_value = sum(
            float(entry.entry_price)
            * float(entry.remaining_quantity or 0)
            for entry in entries
        )

        if weighted_value <= 0:
            return

        average_price = weighted_value / total_quantity

        cycle.average_entry_price = average_price
        cycle.total_filled_quantity = total_quantity

        if cycle.direction == "LONG":

            adverse_percent = (
                (average_price - price) / average_price
            ) * 100

            profit_percent = (
                (price - average_price) / average_price
            ) * 100

        elif cycle.direction == "SHORT":

            adverse_percent = (
                (price - average_price) / average_price
            ) * 100

            profit_percent = (
                (average_price - price) / average_price
            ) * 100

        else:
            logger.error("Invalid direction: %s", cycle.direction)
            return

        self._record_warning(
            db,
            cycle,
            price,
            adverse_percent,
        )

        # انفرادی Entry کا Stop Loss پہلے چیک ہوگا۔
        stop_result = stop_loss_manager.process_cycle(
            db=db,
            cycle=cycle,
            current_price=price,
        )

        if stop_result.get("triggered_entries", 0) > 0:
            db.commit()
            return

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
            db.commit()
            return

        # اگر TP مکمل ہو تو مزید خودکار Entry نہیں لگے گی۔
        tp_result = take_profit_manager.process_cycle(
            db=db,
            cycle=cycle,
            current_price=price,
        )

        if tp_result.get("triggered"):
            db.commit()
            return

        # مخالف سمت کی Entry پہلے، پھر Averaging۔
        # دونوں Thresholds تک قیمت پہنچنے پر دونوں مراحل چل سکتے ہیں۔
        if adverse_percent >= cycle.opposite_percent:

            opposite_result = (
                opposite_position_manager.process_cycle(
                    db,
                    cycle,
                    adverse_percent,
                )
            )

            db.commit()

            if opposite_result.get("triggered"):
                return

        if adverse_percent >= cycle.averaging_percent:

            averaging_result = (
                averaging_manager.process_cycle(
                    db,
                    cycle,
                    adverse_percent,
                )
            )

            db.commit()

        db.commit()

    @staticmethod
    def _record_warning(
        db,
        cycle,
        price,
        adverse_percent,
    ):

        if adverse_percent < cycle.warning_percent:
            return

        if cycle.warning_triggered:
            return

        cycle.warning_triggered = True

        event = CycleEvent(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            event_type="WARNING",
            price=price,
            percentage=adverse_percent,
            status="RECORDED",
            message="Warning threshold reached.",
            idempotency_key=f"cycle-{cycle.id}-warning",
            created_at=datetime.now(timezone.utc),
        )

        db.add(event)
        db.commit()


trading_engine = TradingEngine()
