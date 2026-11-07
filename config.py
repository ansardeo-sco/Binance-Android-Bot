
import os
from dotenv import load_dotenv

load_dotenv()


def get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


class Settings:

    PROJECT_NAME = "Binance Android Futures Trading Bot"
    VERSION = "2.0.0"

    ENVIRONMENT = os.getenv(
        "ENVIRONMENT",
        "development",
    ).strip().lower()

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./trading_bot.db",
    )

    BINANCE_API_KEY = os.getenv(
        "BINANCE_API_KEY",
        "",
    ).strip()

    BINANCE_API_SECRET = os.getenv(
        "BINANCE_API_SECRET",
        "",
    ).strip()

    BINANCE_USE_TESTNET = get_bool(
        "BINANCE_USE_TESTNET",
        True,
    )

    LIVE_TRADING_ENABLED = get_bool(
        "LIVE_TRADING_ENABLED",
        False,
    )

    BOT_ADMIN_TOKEN = os.getenv(
        "BOT_ADMIN_TOKEN",
        "",
    ).strip()

    DEFAULT_MARGIN_MODE = "ISOLATED"
    DEFAULT_POSITION_MODE = "HEDGE"

    DEFAULT_INITIAL_MARGIN = 2.0
    DEFAULT_AVERAGING_MARGIN = 2.0
    DEFAULT_OPPOSITE_MARGIN = 2.0

    DEFAULT_LEVERAGE = 6
    MAX_LEVERAGE = 20

    DEFAULT_TP_PERCENT = 3.0
    DEFAULT_SL_PERCENT = 12.0

    DEFAULT_WARNING_PERCENT = 6.0
    DEFAULT_OPPOSITE_PERCENT = 7.0
    DEFAULT_AVERAGING_PERCENT = 9.0
    DEFAULT_REENTRY_PERCENT = 1.0

    ALLOWED_SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
    ]

    MARKET_POLL_INTERVAL = 10

    API_PREFIX = "/api/v1"

    MIN_MARGIN_USDT = 1.0
    MAX_MARGIN_USDT = 100.0

    MAX_ACTIVE_CYCLES_PER_SYMBOL = 2

    ORDER_RETRY_LIMIT = 3
    ORDER_STATUS_CHECK_REQUIRED = True

    NOTIFICATIONS_ENABLED = True

    @property
    def trading_mode(self):

        if (
            self.BINANCE_USE_TESTNET
            and not self.LIVE_TRADING_ENABLED
        ):
            return "TESTNET"

        return "DISABLED"

    def validate_trading_mode(self):

        if not self.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "Production Binance access is blocked. "
                "Only Binance Testnet is permitted."
            )

        if self.LIVE_TRADING_ENABLED:
            raise RuntimeError(
                "Live trading is blocked in this development version."
            )


settings = Settings()
