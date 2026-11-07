import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import engine, Base, get_db
from models import TradingCycle, CycleEntry
from binance_client import binance_client
from engine import trading_engine
from order_manager import order_manager
from risk_manager import risk_manager


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(trading_engine.start())

    yield

    trading_engine.stop()
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    binance_client.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Binance USDⓈ-M Futures Trading Bot",
    lifespan=lifespan,
)


class InitialEntryRequest(BaseModel):
    symbol: str
    direction: str

    initial_margin: float = Field(
        default=settings.DEFAULT_INITIAL_MARGIN,
        gt=0,
    )

    leverage: int = Field(
        default=settings.DEFAULT_LEVERAGE,
        ge=1,
    )


@app.get("/")
def read_root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "Running",
        "trading_mode": settings.trading_mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    return {
        "status": (
            "healthy"
            if database_status == "connected"
            else "unhealthy"
        ),
        "database": database_status,
        "trading_mode": settings.trading_mode,
        "testnet": settings.BINANCE_USE_TESTNET,
        "engine_running": trading_engine.running,
    }


@app.get(f"{settings.API_PREFIX}/balance")
def get_balance():
    result = binance_client.verify_connection()

    if result.get("status") != "Connected":
        raise HTTPException(
            status_code=503,
            detail=result.get(
                "error",
                "Binance account is not connected",
            ),
        )

    return {
        "balance": result.get("free_usdt", 0.0),
        "total_balance": result.get("total_usdt", 0.0),
        "currency": "USDT",
        "testnet": result.get("testnet", True),
    }


@app.post(f"{settings.API_PREFIX}/trade/initial-entry")
def create_initial_entry(
    request: InitialEntryRequest,
    db: Session = Depends(get_db),
):
    try:
        validated = risk_manager.validate_initial_entry(
            symbol=request.symbol,
            direction=request.direction,
            margin=request.initial_margin,
            leverage=request.leverage,
        )

        new_cycle = TradingCycle(
            symbol=validated["symbol"],
            direction=validated["direction"],
            status="ACTIVE",
            initial_margin=validated["margin"],
            averaging_margin=settings.DEFAULT_AVERAGING_MARGIN,
            opposite_margin=settings.DEFAULT_OPPOSITE_MARGIN,
            leverage=validated["leverage"],
            tp_percent=settings.DEFAULT_TP_PERCENT,
            sl_percent=settings.DEFAULT_SL_PERCENT,
            warning_percent=settings.DEFAULT_WARNING_PERCENT,
            opposite_percent=settings.DEFAULT_OPPOSITE_PERCENT,
            averaging_percent=settings.DEFAULT_AVERAGING_PERCENT,
            reentry_percent=settings.DEFAULT_REENTRY_PERCENT,
        )

        db.add(new_cycle)
        db.commit()
        db.refresh(new_cycle)

        result = order_manager.place_initial_entry(
            db,
            new_cycle,
        )

        return {
            "message": "Initial entry request processed.",
            "cycle_id": new_cycle.id,
            "symbol": new_cycle.symbol,
            "direction": new_cycle.direction,
            "status": new_cycle.status,
            "order_placed": True,
            "order": result,
        }

    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except Exception as error:
        db.rollback()
        logger.exception("Initial entry request failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to process initial entry.",
        )


@app.get(f"{settings.API_PREFIX}/cycles/active")
def get_active_cycles(
    db: Session = Depends(get_db),
):
    cycles = (
        db.query(TradingCycle)
        .filter(TradingCycle.status == "ACTIVE")
        .order_by(TradingCycle.created_at.desc())
        .all()
    )

    return {
        "active_cycles_count": len(cycles),
        "cycles": [
            {
                "id": cycle.id,
                "symbol": cycle.symbol,
                "direction": cycle.direction,
                "status": cycle.status,
                "average_entry_price": cycle.average_entry_price,
                "total_filled_quantity": cycle.total_filled_quantity,
                "created_at": (
                    cycle.created_at.isoformat()
                    if cycle.created_at
                    else None
                ),
            }
            for cycle in cycles
        ],
    }


@app.get(f"{settings.API_PREFIX}/cycles/{{cycle_id}}")
def get_cycle(
    cycle_id: int,
    db: Session = Depends(get_db),
):
    cycle = (
        db.query(TradingCycle)
        .filter(TradingCycle.id == cycle_id)
        .first()
    )

    if not cycle:
        raise HTTPException(
            status_code=404,
            detail="Trading cycle not found.",
        )

    entries = (
        db.query(CycleEntry)
        .filter(CycleEntry.cycle_id == cycle.id)
        .all()
    )

    return {
        "cycle_id": cycle.id,
        "symbol": cycle.symbol,
        "direction": cycle.direction,
        "status": cycle.status,
        "average_entry_price": cycle.average_entry_price,
        "entries": [
            {
                "id": entry.id,
                "type": entry.entry_type,
                "status": entry.status,
                "entry_price": entry.entry_price,
                "filled_quantity": entry.filled_quantity,
                "remaining_quantity": entry.remaining_quantity,
            }
            for entry in entries
        ],
    }
