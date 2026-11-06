
import asyncio
import ccxt
from config import settings


class BinanceFuturesClient:

    def __init__(self):
        self.exchange = ccxt.binance({
            "apiKey": settings.BINANCE_API_KEY,
            "secret": settings.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future"
            }
        })

        if settings.BINANCE_USE_TESTNET:
            self.exchange.set_sandbox_mode(True)

    def _fetch_mark_price_sync(self, symbol: str) -> float:
        self.exchange.load_markets()
        market = self.exchange.market(symbol)

        response = self.exchange.request(
            "premiumIndex",
            "fapiPublic",
            "GET",
            {"symbol": market["id"]}
        )

        return float(response["markPrice"])

    async def get_market_price(self, symbol: str) -> float:
        try:
            return await asyncio.to_thread(
                self._fetch_mark_price_sync,
                symbol
            )
        except Exception as e:
            print(f"Market price error for {symbol}: {e}")
            return 0.0

    def verify_connection(self):
        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            return {
                "status": "Disconnected",
                "error": "Binance API credentials are not configured",
                "testnet": settings.BINANCE_USE_TESTNET
            }

        try:
            balance = self.exchange.fetch_balance({
                "type": "future"
            })

            usdt = balance.get("USDT", {})

            return {
                "status": "Connected",
                "testnet": settings.BINANCE_USE_TESTNET,
                "free_usdt": float(usdt.get("free") or 0),
                "total_usdt": float(usdt.get("total") or 0)
            }

        except Exception as e:
            return {
                "status": "Disconnected",
                "testnet": settings.BINANCE_USE_TESTNET,
                "error": str(e)
            }
