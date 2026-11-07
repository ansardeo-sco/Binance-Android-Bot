import asyncio
import logging
from typing import Any, Dict

import ccxt

from config import settings


logger = logging.getLogger(__name__)


class BinanceFuturesClient:

    def __init__(self):
        self.exchange = ccxt.binance({
            "apiKey": settings.BINANCE_API_KEY,
            "secret": settings.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        })

        if settings.BINANCE_USE_TESTNET:
            self.exchange.set_sandbox_mode(True)

        self._markets_loaded = False

    def _load_markets_sync(self):
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def _fetch_mark_price_sync(self, symbol: str) -> float:
        self._load_markets_sync()

        market = self.exchange.market(symbol)

        response = self.exchange.request(
            "premiumIndex",
            "fapiPublic",
            "GET",
            {"symbol": market["id"]},
        )

        mark_price = response.get("markPrice")

        if mark_price is None:
            raise ValueError(
                f"Mark price unavailable for {symbol}"
            )

        price = float(mark_price)

        if price <= 0:
            raise ValueError(
                f"Invalid mark price received for {symbol}"
            )

        return price

    async def get_market_price(self, symbol: str) -> float:
        try:
            return await asyncio.to_thread(
                self._fetch_mark_price_sync,
                symbol,
            )

        except Exception as error:
            logger.error(
                "Market price error for %s: %s",
                symbol,
                error,
            )
            raise

    def _verify_connection_sync(self) -> Dict[str, Any]:

        if (
            not settings.BINANCE_API_KEY
            or not settings.BINANCE_API_SECRET
        ):
            return {
                "status": "Disconnected",
                "error": "Binance API credentials are not configured",
                "testnet": settings.BINANCE_USE_TESTNET,
                "trading_mode": settings.trading_mode,
            }

        try:
            balance = self.exchange.fetch_balance({
                "type": "future",
            })

            usdt = balance.get("USDT", {})

            return {
                "status": "Connected",
                "testnet": settings.BINANCE_USE_TESTNET,
                "trading_mode": settings.trading_mode,
                "free_usdt": float(usdt.get("free") or 0),
                "total_usdt": float(usdt.get("total") or 0),
            }

        except Exception as error:
            logger.error(
                "Binance connection error: %s",
                error,
            )

            return {
                "status": "Disconnected",
                "testnet": settings.BINANCE_USE_TESTNET,
                "trading_mode": settings.trading_mode,
                "error": str(error),
            }

    def verify_connection(self) -> Dict[str, Any]:
        return self._verify_connection_sync()

    async def get_balance(self) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._verify_connection_sync
        )

    def close(self):
        try:
            self.exchange.close()
        except Exception as error:
            logger.warning(
                "Exchange close warning: %s",
                error,
            )


binance_client = BinanceFuturesClient()
