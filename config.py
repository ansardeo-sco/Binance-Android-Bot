
import os
from dotenv import load_dotenv

load_dotenv()


def get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


class Settings:
    # Project
    PROJECT_NAME = "Binance Android Futures Trading Bot"
    VERSION = "2.0.0"

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()

    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./trading_bot.db"
    )

    # Binance API credentials
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()

    # Safety: Testnet is enabled by default.
    BINANCE_USE_TESTNET = get_bool("BINANCE_USE_TESTNET", True)

    # Live trading must be explicitly enabled on the server.
    LIVE_TRADING_ENABLED = get_bool("LIVE_TRADING_ENABLED", False)

    # Trading mode
    DEFAULT_MARGIN_MODE = "ISOLATED"
    DEFAULT_POSITION_MODE = "HEDGE"

    # Default margins (USDT)
    DEFAULT_INITIAL_MARGIN = 2.0
    DEFAULT_AVERAGING_MARGIN = 2.0
    DEFAULT_OPPOSITE_MARGIN = 2.0

    # Leverage
    DEFAULT_LEVERAGE = 6
    MAX_LEVERAGE = 20

    # Trading percentages
    DEFAULT_TP_PERCENT = 3.0
    DEFAULT_SL_PERCENT = 12.0
    DEFAULT_WARNING_PERCENT = 6.0
    DEFAULT_OPPOSITE_PERCENT = 7.0
    DEFAULT_AVERAGING_PERCENT = 9.0
    DEFAULT_REENTRY_PERCENT = 1.0

    # Supported initial trading symbols
    ALLOWED_SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
    ]

    # Market monitoring
    MARKET_POLL_INTERVAL = 10

    # API
    API_PREFIX = "/api/v1"

    # Risk protection
    MIN_MARGIN_USDT = 1.0
    MAX_MARGIN_USDT = 100.0
    MAX_ACTIVE_CYCLES_PER_SYMBOL = 2

    # Order safety
    ORDER_RETRY_LIMIT = 3
    ORDER_STATUS_CHECK_REQUIRED = True

    # Notifications
    NOTIFICATIONS_ENABLED = True

    @property
    def trading_mode(self):
        if self.BINANCE_USE_TESTNET:
            return "TESTNET"

        if self.LIVE_TRADING_ENABLED:
            return "LIVE"

        return "DISABLED"

    def validate_trading_mode(self):
        if not self.BINANCE_USE_TESTNET and not self.LIVE_TRADING_ENABLED:
            raise RuntimeError(
                "Trading is disabled. Enable Testnet or explicitly authorize Live trading."
            )

        if self.BINANCE_USE_TESTNET and self.LIVE_TRADING_ENABLED:
            raise RuntimeError(
                "Invalid configuration: Testnet and Live trading cannot be enabled together."
            )


settings = Settings()
