from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class TradingCycle(Base):
    __tablename__ = "trading_cycles"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, unique=True, index=True)  # e.g., BTCUSDT-LONG-001
    symbol = Column(String, index=True)                 # e.g., BTCUSDT
    direction = Column(String)                          # LONG or SHORT
    status = Column(String, default="ACTIVE")           # ACTIVE, COMPLETED, STOPPED
    
    # Settings Snapshot for this cycle
    initial_margin = Column(Float)
    averaging_margin = Column(Float)
    opposite_margin = Column(Float)
    leverage = Column(Integer)
    tp_percent = Column(Float)
    sl_percent = Column(Float)
    warning_percent = Column(Float)
    opposite_percent = Column(Float)
    averaging_percent = Column(Float)
    reentry_percent = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    entries = relationship("CycleEntry", back_populates="cycle")
    orders = relationship("CycleOrder", back_populates="cycle")

class CycleEntry(Base):
    __tablename__ = "cycle_entries"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, ForeignKey("trading_cycles.cycle_id"))
    entry_type = Column(String)  # INITIAL, AVERAGING, OPPOSITE
    entry_price = Column(Float)
    quantity = Column(Float)
    leverage = Column(Integer)
    margin = Column(Float)
    stop_loss_price = Column(Float)
    status = Column(String, default="FILLED")  # PENDING, FILLED, CLOSED
    created_at = Column(DateTime, default=datetime.utcnow)

    cycle = relationship("TradingCycle", back_populates="entries")

class CycleOrder(Base):
    __tablename__ = "cycle_orders"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String, ForeignKey("trading_cycles.cycle_id"))
    order_id = Column(String, unique=True)
    symbol = Column(String)
    side = Column(String)       # BUY or SELL
    order_type = Column(String) # MARKET or LIMIT
    price = Column(Float)
    quantity = Column(Float)
    status = Column(String)     # NEW, FILLED, CANCELED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)

    cycle = relationship("TradingCycle", back_populates="orders")
