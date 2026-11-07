from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class TradingCycle(Base):
    __tablename__ = "trading_cycles"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(30), nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)

    status = Column(
        String(20),
        nullable=False,
        default="ACTIVE",
        index=True,
    )

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

    average_entry_price = Column(Float, nullable=True)
    total_filled_quantity = Column(Float, nullable=False, default=0.0)

    take_profit_price = Column(Float, nullable=True)
    reentry_price = Column(Float, nullable=True)

    warning_triggered = Column(Boolean, nullable=False, default=False)
    opposite_triggered = Column(Boolean, nullable=False, default=False)
    averaging_triggered = Column(Boolean, nullable=False, default=False)

    opposite_cycle_id = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)


class CycleEntry(Base):
    __tablename__ = "cycle_entries"

    id = Column(Integer, primary_key=True, index=True)

    cycle_id = Column(
        Integer,
        ForeignKey("trading_cycles.id"),
        nullable=False,
        index=True,
    )

    symbol = Column(String(30), nullable=False, index=True)
    direction = Column(String(10), nullable=False)

    entry_type = Column(
        String(20),
        nullable=False,
        default="INITIAL",
    )

    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True,
    )

    requested_margin = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)

    requested_quantity = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=False, default=0.0)

    entry_price = Column(Float, nullable=True)
    remaining_quantity = Column(Float, nullable=False, default=0.0)

    stop_loss_percent = Column(Float, nullable=False, default=12.0)
    stop_loss_price = Column(Float, nullable=True)

    exchange_order_id = Column(String(100), nullable=True, index=True)
    client_order_id = Column(String(100), nullable=True, unique=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class CycleOrder(Base):
    __tablename__ = "cycle_orders"

    id = Column(Integer, primary_key=True, index=True)

    cycle_id = Column(
        Integer,
        ForeignKey("trading_cycles.id"),
        nullable=False,
        index=True,
    )

    entry_id = Column(
        Integer,
        ForeignKey("cycle_entries.id"),
        nullable=True,
        index=True,
    )

    symbol = Column(String(30), nullable=False, index=True)

    order_type = Column(String(30), nullable=False)
    side = Column(String(10), nullable=False)

    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True,
    )

    requested_quantity = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=False, default=0.0)

    average_fill_price = Column(Float, nullable=True)

    exchange_order_id = Column(String(100), nullable=True, index=True)
    client_order_id = Column(String(100), nullable=False, unique=True)

    reduce_position = Column(Boolean, nullable=False, default=False)

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class CycleEvent(Base):
    __tablename__ = "cycle_events"

    id = Column(Integer, primary_key=True, index=True)

    cycle_id = Column(
        Integer,
        ForeignKey("trading_cycles.id"),
        nullable=False,
        index=True,
    )

    symbol = Column(String(30), nullable=False, index=True)

    event_type = Column(String(40), nullable=False, index=True)

    price = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)

    status = Column(String(20), nullable=False, default="RECORDED")

    message = Column(Text, nullable=True)

    idempotency_key = Column(String(150), nullable=True, unique=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)


class ReentryRecord(Base):
    __tablename__ = "reentry_records"

    id = Column(Integer, primary_key=True, index=True)

    cycle_id = Column(
        Integer,
        ForeignKey("trading_cycles.id"),
        nullable=False,
        index=True,
    )

    symbol = Column(String(30), nullable=False, index=True)
    direction = Column(String(10), nullable=False)

    reference_close_price = Column(Float, nullable=False)
    trigger_price = Column(Float, nullable=False)

    status = Column(
        String(20),
        nullable=False,
        default="WAITING",
        index=True,
    )

    new_cycle_id = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    triggered_at = Column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    cycle_id = Column(
        Integer,
        ForeignKey("trading_cycles.id"),
        nullable=True,
        index=True,
    )

    symbol = Column(String(30), nullable=True, index=True)

    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)

    notification_type = Column(String(40), nullable=False)

    is_read = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=utc_now)


class ExchangePosition(Base):
    __tablename__ = "exchange_positions"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(30), nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)

    exchange_position_key = Column(String(120), nullable=False, unique=True)

    exchange_quantity = Column(Float, nullable=False, default=0.0)
    entry_price = Column(Float, nullable=True)
    mark_price = Column(Float, nullable=True)

    unrealized_pnl = Column(Float, nullable=True)

    last_synced_at = Column(DateTime(timezone=True), default=utc_now)


class BotEvent(Base):
    __tablename__ = "bot_events"

    id = Column(Integer, primary_key=True, index=True)

    event_type = Column(String(50), nullable=False, index=True)

    severity = Column(String(20), nullable=False, default="INFO")

    symbol = Column(String(30), nullable=True, index=True)
    cycle_id = Column(Integer, nullable=True, index=True)

    message = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utc_now)


Index(
    "ix_cycle_symbol_direction_status",
    TradingCycle.symbol,
    TradingCycle.direction,
    TradingCycle.status,
)

Index(
    "ix_entry_cycle_status",
    CycleEntry.cycle_id,
    CycleEntry.status,
)

Index(
    "ix_order_cycle_status",
    CycleOrder.cycle_id,
    CycleOrder.status,
)

Index(
    "ix_event_cycle_type",
    CycleEvent.cycle_id,
    CycleEvent.event_type,
    )
