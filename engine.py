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
)
from binance_client import binance_client


logger = logging.getLogger(__name__)


class TradingEngine:

    def __init__(self):
        self.running = False
        self._lock = asyncio.Lock()

    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info("Trading engine started")

        while self.running:
            try:
                await self.process_active_cycles()

            except Exception:
                logger.exception("Trading engine processing error")

            await asyncio.sleep(
                settings.MARKET_POLL_INTERVAL
            )

    def stop(self):
        self.running = False
        logger.info("Trading engine stopped")

    async def process_active_cycles(self):
        async with self._lock:
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
                        logger.exception(
                            "Cycle processing failed: %s",
                            cycle.id,
                        )

            finally:
                db.close()

    async def process_cycle(
        self,
        db: Session,
        cycle: TradingCycle,
    ):
        price = await binance_client.get_market_price(
            cycle.symbol
        )

        if price <= 0:
            return

        entries = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.status == "FILLED",
                CycleEntry.remaining_quantity > 0,
            )
            .all()
        )

        if not entries:
            return

        total_quantity = sum(
            entry.remaining_quantity
            for entry in entries
        )

        if total_quantity <= 0:
            return

        weighted_value = sum(
            entry.entry_price * entry.remaining_quantity
            for entry in entries
            if entry.entry_price is not None
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
            logger.error(
                "Invalid cycle direction: %s",
                cycle.direction,
            )
            return

        await self._record_triggers(
            db=db,
            cycle=cycle,
            price=price,
            adverse_percent=adverse_percent,
        )

        if profit_percent >= cycle.tp_percent:
            self._record_event(
                db,
                cycle,
                "TAKE_PROFIT_REACHED",
                price,
                profit_percent,
                "Take profit threshold reached. "
                "Actual order execution is not enabled in this engine.",
            )

        for entry in entries:
            if not entry.entry_price:
                continue

            if cycle.direction == "LONG":
                entry_loss = (
                    (entry.entry_price - price)
                    / entry.entry_price
                ) * 100

                stop_price = entry.entry_price * (
                    1 - entry.stop_loss_percent / 100
                )

            else:
                entry_loss = (
                    (price - entry.entry_price)
                    / entry.entry_price
                ) * 100

                stop_price = entry.entry_price * (
                    1 + entry.stop_loss_percent / 100
                )

            entry.stop_loss_price = stop_price

            if entry_loss >= entry.stop_loss_percent:
                self._record_event(
                    db,
                    cycle,
                    "ENTRY_STOP_LOSS_REACHED",
                    price,
                    entry_loss,
                    f"Entry {entry.id} stop-loss threshold reached. "
                    "Actual closing order is not enabled.",
                )

        db.commit()

    async def _record_triggers(
        self,
        db: Session,
        cycle: TradingCycle,
        price: float,
        adverse_percent: float,
    ):

        triggers = [
            (
                cycle.warning_percent,
                "WARNING",
                "warning_triggered",
            ),
            (
                cycle.opposite_percent,
                "OPPOSITE_TRIGGER",
                "opposite_triggered",
            ),
            (
                cycle.averaging_percent,
                "AVERAGING_TRIGGER",
                "averaging_triggered",
            ),
        ]

        for threshold, event_type, flag_name in triggers:

            if adverse_percent < threshold:
                continue

            if getattr(cycle, flag_name):
                continue

            setattr(cycle, flag_name, True)

            self._record_event(
                db,
                cycle,
                event_type,
                price,
                adverse_percent,
                f"{event_type} threshold reached. "
                "Order execution is handled by the order manager.",
            )

    @staticmethod
    def _record_event(
        db: Session,
        cycle: TradingCycle,
        event_type: str,
        price: float,
        percentage: float,
        message: str,
    ):

        event_key = (
            f"cycle-{cycle.id}-{event_type}"
        )

        existing = (
            db.query(CycleEvent)
            .filter(
                CycleEvent.idempotency_key == event_key
            )
            .first()
        )

        if existing:
            return

        event = CycleEvent(
            cycle_id=cycle.id,
            symbol=cycle.symbol,
            event_type=event_type,
            price=price,
            percentage=percentage,
            status="RECORDED",
            message=message,
            idempotency_key=event_key,
            created_at=datetime.now(timezone.utc),
        )

        db.add(event)


trading_engine = TradingEngine()
