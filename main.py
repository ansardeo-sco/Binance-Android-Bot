
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
import asyncio

from config import settings
from database import engine, Base, get_db
import models
from engine import engine as trading_engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Automated Trading Management Bot for Binance USDⓈ-M Futures"
)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(trading_engine.monitor_market())


class InitialEntryRequest(BaseModel):
    symbol: str
    direction: str
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
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    return {
        "status": "healthy" if database_status == "connected" else "unhealthy",
        "database": database_status,
        "testnet_mode": settings.BINANCE_USE_TESTNET,
        "binance_connection": trading_engine.client.verify_connection()
    }


@app.get("/api/v1/balance")
def get_balance():
    result = trading_engine.client.verify_connection()

    if result.get("status") != "Connected":
        raise HTTPException(
            status_code=503,
            detail=result.get("error", "Binance account is not connected")
        )

    return {
        "balance": result.get("free_usdt", 0.0),
        "total_balance": result.get("total_usdt", 0.0),
        "currency": "USDT",
        "testnet": result.get("testnet", True)
    }


@app.post("/api/v1/trade/initial-entry")
def create_initial_entry(
    request: InitialEntryRequest,
    db: Session = Depends(get_db)
):
    symbol_upper = request.symbol.upper().strip()
    direction_upper = request.direction.upper().strip()

    if not symbol_upper.endswith("USDT"):
        raise HTTPException(
            status_code=400,
            detail="Only USDT-margined symbols are supported"
        )

    if direction_upper not in ["LONG", "SHORT"]:
        raise HTTPException(
            status_code=400,
            detail="Direction must be LONG or SHORT"
        )

    if request.initial_margin <= 0:
        raise HTTPException(
            status_code=400,
            detail="Initial margin must be greater than zero"
        )

    if request.leverage < 1 or request.leverage > 20:
        raise HTTPException(
            status_code=400,
            detail="Leverage must be between 1 and 20"
        )

    existing_count = db.query(models.TradingCycle).filter(
        models.TradingCycle.symbol == symbol_upper,
        models.TradingCycle.direction == direction_upper
    ).count()

    sequence_num = existing_count + 1
    cycle_id = f"{symbol_upper}-{direction_upper}-{sequence_num:03d}"

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
        "message": "Cycle registered. No Binance order has been placed.",
        "cycle_id": cycle_id,
        "symbol": symbol_upper,
        "direction": direction_upper,
        "leverage": request.leverage,
        "initial_margin": request.initial_margin,
        "status": "ACTIVE",
        "order_placed": False
    }


@app.get("/api/v1/cycles/active")
def get_active_cycles(db: Session = Depends(get_db)):
    active_cycles = db.query(models.TradingCycle).filter(
        models.TradingCycle.status == "ACTIVE"
    ).all()

    return {
        "active_cycles_count": len(active_cycles),
        "cycles": active_cycles
    }
