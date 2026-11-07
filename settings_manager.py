
import math

from sqlalchemy.orm import Session

from config import settings
from bot_settings_model import BotSymbolSettings


DEFAULT_SYMBOL_SETTINGS = {
    "enabled_long": True,
    "enabled_short": True,
    "initial_margin": 2.0,
    "averaging_margin": 2.0,
    "opposite_margin": 2.0,
    "leverage": 6,
    "tp_percent": 3.0,
    "sl_percent": 12.0,
    "warning_percent": 6.0,
    "opposite_percent": 7.0,
    "averaging_percent": 9.0,
    "reentry_percent": 1.0,
}


SETTING_FIELDS = set(DEFAULT_SYMBOL_SETTINGS.keys())


class SettingsManager:

    @staticmethod
    def validate_symbol(symbol):
        if not isinstance(symbol, str):
            raise ValueError("Symbol must be text.")

        symbol = symbol.strip().upper()

        if symbol not in settings.ALLOWED_SYMBOLS:
            raise ValueError("Unsupported trading symbol.")

        return symbol

    @staticmethod
    def serialize(record):
        return {
            "symbol": record.symbol,
            "enabled_long": record.enabled_long,
            "enabled_short": record.enabled_short,
            "initial_margin": record.initial_margin,
            "averaging_margin": record.averaging_margin,
            "opposite_margin": record.opposite_margin,
            "leverage": record.leverage,
            "tp_percent": record.tp_percent,
            "sl_percent": record.sl_percent,
            "warning_percent": record.warning_percent,
            "opposite_percent": record.opposite_percent,
            "averaging_percent": record.averaging_percent,
            "reentry_percent": record.reentry_percent,
            "created_at": (
                record.created_at.isoformat()
                if record.created_at else None
            ),
            "updated_at": (
                record.updated_at.isoformat()
                if record.updated_at else None
            ),
        }

    def get_or_create(self, db: Session, symbol: str):

        symbol = self.validate_symbol(symbol)

        record = (
            db.query(BotSymbolSettings)
            .filter(BotSymbolSettings.symbol == symbol)
            .first()
        )

        if record:
            return record

        record = BotSymbolSettings(
            symbol=symbol,
            **DEFAULT_SYMBOL_SETTINGS,
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return record

    def get_symbol_settings(self, db: Session, symbol: str):

        record = self.get_or_create(db, symbol)

        return self.serialize(record)

    def get_all_settings(self, db: Session):

        result = []

        for symbol in settings.ALLOWED_SYMBOLS:
            record = self.get_or_create(db, symbol)
            result.append(self.serialize(record))

        return {
            "count": len(result),
            "settings": result,
        }

    @staticmethod
    def validate_updates(updates):

        if not isinstance(updates, dict) or not updates:
            raise ValueError("No settings were supplied.")

        unknown_fields = set(updates.keys()) - SETTING_FIELDS

        if unknown_fields:
            raise ValueError(
                "Unsupported settings: "
                + ", ".join(sorted(unknown_fields))
            )

        validated = {}

        for field, value in updates.items():

            if field in ("enabled_long", "enabled_short"):

                if not isinstance(value, bool):
                    raise ValueError(
                        f"{field} must be true or false."
                    )

                validated[field] = value
                continue

            if isinstance(value, bool):
                raise ValueError(
                    f"{field} must be a number."
                )

            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"{field} must be a valid number."
                )

            if not math.isfinite(number):
                raise ValueError(
                    f"{field} must be finite."
                )

            if field in (
                "initial_margin",
                "averaging_margin",
                "opposite_margin",
            ):

                if not (
                    settings.MIN_MARGIN_USDT
                    <= number
                    <= settings.MAX_MARGIN_USDT
                ):
                    raise ValueError(
                        f"{field} must be between "
                        f"{settings.MIN_MARGIN_USDT} and "
                        f"{settings.MAX_MARGIN_USDT} USDT."
                    )

                validated[field] = number
                continue

            if field == "leverage":

                if not number.is_integer():
                    raise ValueError(
                        "Leverage must be a whole number."
                    )

                if not (
                    1 <= number <= settings.MAX_LEVERAGE
                ):
                    raise ValueError(
                        f"Leverage must be between 1 and "
                        f"{settings.MAX_LEVERAGE}."
                    )

                validated[field] = int(number)
                continue

            if field in (
                "tp_percent",
                "sl_percent",
                "warning_percent",
                "opposite_percent",
                "averaging_percent",
                "reentry_percent",
            ):

                if not 0.1 <= number <= 100:
                    raise ValueError(
                        f"{field} must be between 0.1 and 100 percent."
                    )

                validated[field] = number

        return validated

    def update_symbol_settings(
        self,
        db: Session,
        symbol: str,
        updates: dict,
    ):

        record = self.get_or_create(db, symbol)

        validated = self.validate_updates(updates)

        new_long = validated.get(
            "enabled_long",
            record.enabled_long,
        )

        new_short = validated.get(
            "enabled_short",
            record.enabled_short,
        )

        if not new_long and not new_short:
            raise ValueError(
                "At least one direction must remain enabled."
            )

        try:

            for field, value in validated.items():
                setattr(record, field, value)

            db.commit()
            db.refresh(record)

            return self.serialize(record)

        except Exception:
            db.rollback()
            raise


settings_manager = SettingsManager()
