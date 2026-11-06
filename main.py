from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel

from config import settings
from database import engine, Base, get_db
import models

# Create database tables automatically on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Automated Trading Management Bot for Binance USDⓈ-M Futures"
)

# Pydantic models for request validation
class InitialEntryRequest(BaseModel):
    symbol: str
    direction: str  # LONG or SHORT
    initial_margin: float = settings.DEFAULT_INITIAL_MARGIN
    leverage: int = settings.DEFAULT_LEVERAGE

@app.get("/")
def read_root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "Running",
        "timestamp": datetime.utcnow()
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    return {
        "status": "healthy",
        "database": "connected",
        "testnet_mode": settings.BINANCE_USE_TESTNET
    }

@app.post("/api/v1/trade/initial-entry")
def create_initial_entry(request: InitialEntryRequest, db: Session = Depends(get_db)):
    """
    Endpoint for taking initial manual entry and starting a new trading cycle.
    """
    # Generate unique cycle ID e.g., BTCUSDT-LONG-001
    symbol_upper = request.symbol.upper()
    direction_upper = request.direction.upper()
    
    # Count existing cycles for this symbol & direction to generate sequence number
    existing_count = db.query(models.TradingCycle).filter(
        models.TradingCycle.symbol == symbol_upper,
        models.TradingCycle.direction == direction_upper
    ).count()
    
    sequence_num = existing_count + 1
    cycle_id = f"{symbol_upper}-{direction_upper}-{sequence_num:03d}"
    
    # Create new cycle with snapshot settings
    new_cycle = models.TradingCycle(
        cycle_id=cycle_id,
        symbol=symbol_upper,
        direction=direction_upper,
        status="ACTIVE",
        initial_margin=request.initial_margin,
        averaging_margin=settings.DEFAULT_AVERAGING_MARGIN,
        opposite_margin=settings.DEFAULT_OPPOSITE_MARGIN,
        leverage=request.leverage,
        tp_percent=settings.DEFAULT_TP_PERCENT,
        sl_percent=settings.DEFAULT_SL_PERCENT,
        warning_percent=settings.DEFAULT_WARNING_PERCENT,
        opposite_percent=settings.DEFAULT_OPPOSITE_PERCENT,
        averaging_percent=settings.DEFAULT_AVERAGING_PERCENT,
        reentry_percent=settings.DEFAULT_REENTRY_PERCENT
    )
    
    db.add(new_cycle)
    db.commit()
    db.refresh(new_cycle)
    
    return {
        "message": "Initial entry cycle registered successfully",
        "cycle_id": cycle_id,
        "symbol": symbol_upper,
        "direction": direction_upper,
        "leverage": request.leverage,
        "initial_margin": request.initial_margin,
        "status": "ACTIVE"
    }

@app.get("/api/v1/cycles/active")
def get_active_cycles(db: Session = Depends(get_db)):
    """
    Get all currently active trading cycles.
    """
    active_cycles = db.query(models.TradingCycle).filter(models.TradingCycle.status == "ACTIVE").all()
    return {
        "active_cycles_count": len(active_cycles),
        "cycles": active_cycles
    }
