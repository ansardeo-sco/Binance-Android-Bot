
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
            "timeout": 20000,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        })

        # Sandbox mode must be configured before loading markets.
        if settings.BINANCE_USE_TESTNET:
            self.exchange.set_sandbox_mode(True)

        self._markets_loaded = False

    def _require_testnet(self):

        if not settings.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "This development version only permits Binance Testnet."
            )

        settings.validate_trading_mode()

    def _load_markets_sync(self):

        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def _validate_symbol(self, symbol: str):

        if not symbol:
            raise ValueError("Trading symbol is required.")

        self._load_markets_sync()

        if symbol not in self.exchange.markets:
            raise ValueError(
                f"Unsupported Binance Futures market: {symbol}"
            )

        market = self.exchange.market(symbol)

        if not market.get("contract"):
            raise ValueError(
                f"{symbol} is not a Futures contract market."
            )

        if market.get("linear") is not True:
            raise ValueError(
                f"{symbol} is not a linear USDT-margined Futures market."
            )

        return market

    def _fetch_mark_price_sync(self, symbol: str) -> float:

        market = self._validate_symbol(symbol)

        response = self.exchange.request(
            "premiumIndex",
            "fapiPublic",
            "GET",
            {
                "symbol": market["id"],
            },
        )

        mark_price = response.get("markPrice")

        if mark_price is None:
            raise ValueError(
                f"Mark price unavailable for {symbol}."
            )

        price = float(mark_price)

        if price <= 0:
            raise ValueError(
                f"Invalid mark price received for {symbol}."
            )

        return price

    async def get_market_price(self, symbol: str) -> float:

        try:
            return await asyncio.to_thread(
                self._fetch_mark_price_sync,
                symbol,
            )

        except Exception:
            logger.exception(
                "Market price request failed for %s.",
                symbol,
            )
            raise

    def _verify_connection_sync(self) -> Dict[str, Any]:

        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            return {
                "status": "Disconnected",
                "error": "Binance API credentials are not configured.",
                "testnet": settings.BINANCE_USE_TESTNET,
                "trading_mode": settings.trading_mode,
            }

        try:
            self._require_testnet()

            balance = self.exchange.fetch_balance({
                "type": "future",
            })

            usdt = balance.get("USDT") or {}

            return {
                "status": "Connected",
                "testnet": True,
                "trading_mode": "TESTNET",
                "free_usdt": float(usdt.get("free") or 0),
                "total_usdt": float(usdt.get("total") or 0),
            }

        except Exception as error:

            logger.exception(
                "Binance Testnet connection verification failed."
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
            result = self.exchange.close()

            if asyncio.iscoroutine(result):
                return result

        except Exception:
            logger.exception(
                "Exchange connection close warning."
            )


binance_client = BinanceFuturesClient()
