from config import settings


class RiskManager:

    @staticmethod
    def validate_initial_entry(
        symbol: str,
        direction: str,
        margin: float,
        leverage: int,
    ):
        symbol = symbol.upper().strip()
        direction = direction.upper().strip()

        if symbol not in settings.ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol not allowed: {symbol}")

        if direction not in ("LONG", "SHORT"):
            raise ValueError("Direction must be LONG or SHORT")

        if margin < settings.MIN_MARGIN_USDT:
            raise ValueError(
                f"Minimum margin is {settings.MIN_MARGIN_USDT} USDT"
            )

        if margin > settings.MAX_MARGIN_USDT:
            raise ValueError(
                f"Maximum margin is {settings.MAX_MARGIN_USDT} USDT"
            )

        if leverage < 1 or leverage > settings.MAX_LEVERAGE:
            raise ValueError(
                f"Leverage must be between 1 and "
                f"{settings.MAX_LEVERAGE}"
            )

        if not settings.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "Live trading is not authorized in this development stage."
            )

        settings.validate_trading_mode()

        return {
            "symbol": symbol,
            "direction": direction,
            "margin": float(margin),
            "leverage": int(leverage),
        }


risk_manager = RiskManager()
