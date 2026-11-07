
import math

from config import settings


class RiskManager:

    @staticmethod
    def validate_initial_entry(
        symbol: str,
        direction: str,
        margin: float,
        leverage: int,
    ):

        if not isinstance(symbol, str):
            raise ValueError("Symbol must be text.")

        if not isinstance(direction, str):
            raise ValueError("Direction must be text.")

        symbol = symbol.upper().strip()
        direction = direction.upper().strip()

        if symbol not in settings.ALLOWED_SYMBOLS:
            raise ValueError(
                f"Symbol is not allowed: {symbol}"
            )

        if direction not in ("LONG", "SHORT"):
            raise ValueError(
                "Direction must be LONG or SHORT."
            )

        try:
            margin = float(margin)
        except (TypeError, ValueError):
            raise ValueError("Margin must be a valid number.")

        if not math.isfinite(margin):
            raise ValueError("Margin must be a finite number.")

        if margin < settings.MIN_MARGIN_USDT:
            raise ValueError(
                f"Minimum margin is {settings.MIN_MARGIN_USDT} USDT."
            )

        if margin > settings.MAX_MARGIN_USDT:
            raise ValueError(
                f"Maximum margin is {settings.MAX_MARGIN_USDT} USDT."
            )

        if isinstance(leverage, bool):
            raise ValueError("Leverage must be a whole number.")

        try:
            numeric_leverage = int(leverage)
        except (TypeError, ValueError):
            raise ValueError("Leverage must be a whole number.")

        if str(leverage).strip() not in (
            str(numeric_leverage),
            f"{numeric_leverage}.0",
        ):
            raise ValueError("Leverage must be a whole number.")

        if (
            numeric_leverage < 1
            or numeric_leverage > settings.MAX_LEVERAGE
        ):
            raise ValueError(
                f"Leverage must be between 1 and "
                f"{settings.MAX_LEVERAGE}."
            )

        # Live trading is deliberately blocked in this development stage.
        if not settings.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "Live trading is not authorized. "
                "Only Binance Testnet is permitted."
            )

        if settings.LIVE_TRADING_ENABLED:
            raise RuntimeError(
                "Invalid configuration: Live trading must remain disabled."
            )

        settings.validate_trading_mode()

        return {
            "symbol": symbol,
            "direction": direction,
            "margin": margin,
            "leverage": numeric_leverage,
        }


risk_manager = RiskManager()
