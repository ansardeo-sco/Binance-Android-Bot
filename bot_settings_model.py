
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
)

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class BotSymbolSettings(Base):
    __tablename__ = "bot_symbol_settings"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(
        String(30),
        nullable=False,
        unique=True,
        index=True,
    )

    enabled_long = Column(Boolean, nullable=False, default=True)
    enabled_short = Column(Boolean, nullable=False, default=True)

    initial_margin = Column(Float, nullable=False, default=2.0)
    averaging_margin = Column(Float, nullable=False, default=2.0)
    opposite_margin = Column(Float, nullable=False, default=2.0)

    leverage = Column(Integer, nullable=False, default=6)

    tp_percent = Column(Float, nullable=False, default=3.0)
    sl_percent = Column(Float, nullable=False, default=12.0)

    warning_percent = Column(Float, nullable=False, default=6.0)
    opposite_percent = Column(Float, nullable=False, default=7.0)
    averaging_percent = Column(Float, nullable=False, default=9.0)
    reentry_percent = Column(Float, nullable=False, default=1.0)

    created_at = Column(DateTime(timezone=True), default=utc_now)

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
