import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import ExchangePosition
from binance_client import binance_client
from config import settings


logger = logging.getLogger(__name__)


class ReconciliationManager:

    def sync_positions(self):
        db = SessionLocal()

        try:
            exchange = binance_client.exchange

            symbols = [
                f"{symbol[:-4]}/USDT:USDT"
                for symbol in settings.ALLOWED_SYMBOLS
            ]

            positions = exchange.fetch_positions(symbols)

            synced = []

            for position in positions:
                info = position.get("info") or {}

                symbol = (
                    position.get("symbol")
                    or info.get("symbol")
                )

                if not symbol:
                    continue

                position_side = str(
                    info.get("positionSide")
                    or position.get("side")
                    or ""
                ).upper()

                if position_side not in ("LONG", "SHORT"):
                    continue

                contracts = position.get("contracts")

                if contracts is None:
                    contracts = info.get("positionAmt", 0)

                quantity = abs(float(contracts or 0))

                entry_price = position.get("entryPrice")
                mark_price = position.get("markPrice")
                unrealized_pnl = position.get("unrealizedPnl")

                position_key = (
                    f"{symbol}:{position_side}"
                )

                record = (
                    db.query(ExchangePosition)
                    .filter(
                        ExchangePosition.exchange_position_key
                        == position_key
                    )
                    .first()
                )

                if not record:
                    record = ExchangePosition(
                        symbol=symbol,
                        direction=position_side,
                        exchange_position_key=position_key,
                    )
                    db.add(record)

                record.exchange_quantity = quantity

                record.entry_price = (
                    float(entry_price)
                    if entry_price is not None
                    else None
                )

                record.mark_price = (
                    float(mark_price)
                    if mark_price is not None
                    else None
                )

                record.unrealized_pnl = (
                    float(unrealized_pnl)
                    if unrealized_pnl is not None
                    else None
                )

                record.last_synced_at = datetime.now(
                    timezone.utc
                )

                synced.append({
                    "symbol": symbol,
                    "direction": position_side,
                    "quantity": quantity,
                    "entry_price": record.entry_price,
                    "mark_price": record.mark_price,
                    "unrealized_pnl": record.unrealized_pnl,
                })

            db.commit()

            return {
                "success": True,
                "positions_synced": len(synced),
                "positions": synced,
            }

        except Exception:
            db.rollback()
            logger.exception("Position reconciliation failed")
            raise

        finally:
            db.close()


reconciliation_manager = ReconciliationManager()
