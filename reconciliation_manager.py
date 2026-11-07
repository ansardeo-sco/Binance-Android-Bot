
import logging
from datetime import datetime, timezone

from database import SessionLocal
from models import ExchangePosition
from binance_client import binance_client
from config import settings


logger = logging.getLogger(__name__)


class ReconciliationManager:

    @staticmethod
    def _symbol_map(exchange):

        mapping = {}

        for raw_symbol in settings.ALLOWED_SYMBOLS:

            unified_symbol = binance_client.get_exchange_symbol(
                raw_symbol
            )

            market = exchange.market(unified_symbol)

            market_id = market.get("id")

            mapping[raw_symbol.upper()] = unified_symbol
            mapping[unified_symbol.upper()] = unified_symbol

            if market_id:
                mapping[str(market_id).upper()] = unified_symbol

        return mapping

    def sync_positions(self):

        # Production account کی پوزیشنز یہاں بھی نہیں پڑھی جائیں گی۔
        settings.validate_trading_mode()

        if not settings.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "Position reconciliation is restricted to Testnet."
            )

        db = SessionLocal()

        try:

            exchange = binance_client.exchange

            binance_client._load_markets_sync()

            symbol_map = self._symbol_map(exchange)

            symbols = sorted({
                symbol_map[raw.upper()]
                for raw in settings.ALLOWED_SYMBOLS
            })

            positions = exchange.fetch_positions(symbols)

            if positions is None:
                raise RuntimeError(
                    "Binance returned no valid position response."
                )

            now = datetime.now(timezone.utc)
            synced = []

            existing_records = (
                db.query(ExchangePosition)
                .filter(
                    ExchangePosition.symbol.in_(symbols)
                )
                .all()
            )

            for record in existing_records:

                record.exchange_quantity = 0.0
                record.unrealized_pnl = 0.0
                record.last_synced_at = now

            for position in positions:

                info = position.get("info") or {}

                raw_symbol = (
                    position.get("symbol")
                    or info.get("symbol")
                )

                if not raw_symbol:
                    continue

                symbol = symbol_map.get(
                    str(raw_symbol).upper()
                )

                if not symbol:
                    logger.warning(
                        "Skipping unrecognized exchange symbol: %s",
                        raw_symbol,
                    )
                    continue

                contracts = position.get("contracts")

                if contracts is None:
                    contracts = info.get("positionAmt", 0)

                quantity = abs(float(contracts or 0))

                position_side = str(
                    info.get("positionSide") or ""
                ).upper()

                if position_side == "BOTH":

                    if quantity > 0:
                        raise RuntimeError(
                            "Binance reports one-way position mode (BOTH). "
                            "This bot requires Hedge Mode."
                        )

                    continue

                if position_side not in ("LONG", "SHORT"):

                    unified_side = str(
                        position.get("side") or ""
                    ).upper()

                    if unified_side in ("LONG", "SHORT"):
                        position_side = unified_side

                    elif quantity > 0:
                        raise RuntimeError(
                            f"Could not determine position side for {symbol}."
                        )

                    else:
                        continue

                position_key = f"{symbol}:{position_side}"

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

                entry_price = position.get("entryPrice")
                mark_price = position.get("markPrice")
                unrealized_pnl = position.get("unrealizedPnl")

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
                    else 0.0
                )

                record.last_synced_at = now

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
                "synced_at": now.isoformat(),
                "trading_mode": "TESTNET",
            }

        except Exception:

            db.rollback()

            logger.exception(
                "Position reconciliation failed."
            )

            raise

        finally:
            db.close()


reconciliation_manager = ReconciliationManager()
