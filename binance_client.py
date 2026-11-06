import ccxt.pro as ccxtpro
import ccxt
from config import settings

class BinanceFuturesClient:
    def __init__(self):
        # Initialize CCXT Binance Futures client (Testnet or Live)
        self.exchange = ccxt.binance({
            'apiKey': settings.BINANCE_API_KEY,
            'secret': settings.BINANCE_API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future', # USDⓈ-M Futures
            }
        })
        
        if settings.BINANCE_USE_TESTNET:
            self.exchange.set_sandbox_mode(True)

    async def get_market_price(self, symbol: str) -> float:
        """
        Fetch the current mark price for a given symbol (e.g., BTCUSDT).
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return 0.0

    def verify_connection(self):
        """
        Verify API connection and account status.
        """
        try:
            balance = self.exchange.fetch_balance()
            return {
                "status": "Connected",
                "testnet": settings.BINANCE_USE_TESTNET,
                "free_usdt": balance.get('USDT', {}).get('free', 0.0)
            }
        except Exception as e:
            return {
                "status": "Disconnected",
                "error": str(e)
            }
