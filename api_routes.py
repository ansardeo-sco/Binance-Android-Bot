
import logging
import secrets

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from config import settings

from models import (
    Notification,
    BotEvent,
    ExchangePosition,
    ReentryRecord,
)

from notification_manager import notification_manager
from order_status_manager import order_status_manager
from reconciliation_manager import reconciliation_manager

from settings_manager import settings_manager


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Bot Management"],
)


class SymbolSettingsUpdate(BaseModel):

    enabled_long: bool | None = None
    enabled_short: bool | None = None

    initial_margin: float | None = Field(default=None, gt=0)
    averaging_margin: float | None = Field(default=None, gt=0)
    opposite_margin: float | None = Field(default=None, gt=0)

    leverage: int | None = Field(default=None, ge=1)

    tp_percent: float | None = Field(default=None, gt=0)
    sl_percent: float | None = Field(default=None, gt=0)

    warning_percent: float | None = Field(default=None, gt=0)
    opposite_percent: float | None = Field(default=None, gt=0)
    averaging_percent: float | None = Field(default=None, gt=0)
    reentry_percent: float | None = Field(default=None, gt=0)


def require_admin_token(
    x_bot_admin_token: str | None = Header(
        default=None,
        alias="X-Bot-Admin-Token",
    ),
):

    configured_token = settings.BOT_ADMIN_TOKEN

    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Settings API is locked. Admin token is not configured.",
        )

    if (
        not x_bot_admin_token
        or not secrets.compare_digest(
            x_bot_admin_token,
            configured_token,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token.",
        )


@router.get("/settings")
def get_all_symbol_settings(
    db: Session = Depends(get_db),
):

    try:
        return settings_manager.get_all_settings(db)

    except Exception as error:

        logger.exception("Unable to load symbol settings.")

        raise HTTPException(
            status_code=500,
            detail="Unable to load symbol settings.",
        ) from error


@router.get("/settings/{symbol}")
def get_symbol_settings(
    symbol: str,
    db: Session = Depends(get_db),
):

    try:
        return settings_manager.get_symbol_settings(
            db,
            symbol,
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:

        logger.exception("Unable to load symbol settings.")

        raise HTTPException(
            status_code=500,
            detail="Unable to load symbol settings.",
        ) from error


@router.put("/settings/{symbol}")
def update_symbol_settings(
    symbol: str,
    request: SymbolSettingsUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
):

    updates = request.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    try:

        return {
            "success": True,
            "message": "Symbol settings saved.",
            "settings": settings_manager.update_symbol_settings(
                db,
                symbol,
                updates,
            ),
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:

        logger.exception("Unable to update symbol settings.")

        raise HTTPException(
            status_code=500,
            detail="Unable to save symbol settings.",
        ) from error


@router.get("/notifications")
def get_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):

    query = db.query(Notification)

    if unread_only:
        query = query.filter(
            Notification.is_read.is_(False)
        )

    records = (
        query.order_by(Notification.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(records),
        "notifications": [
            {
                "id": item.id,
                "symbol": item.symbol,
                "title": item.title,
                "message": item.message,
                "type": item.notification_type,
                "is_read": item.is_read,
                "created_at": (
                    item.created_at.isoformat()
                    if item.created_at else None
                ),
            }
            for item in records
        ],
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
):

    success = notification_manager.mark_as_read(
        db,
        notification_id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Notification not found.",
        )

    return {
        "success": True,
        "notification_id": notification_id,
    }


@router.get("/events")
def get_bot_events(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):

    events = (
        db.query(BotEvent)
        .order_by(BotEvent.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(events),
        "events": [
            {
                "id": event.id,
                "type": event.event_type,
                "severity": event.severity,
                "symbol": event.symbol,
                "cycle_id": event.cycle_id,
                "message": event.message,
                "created_at": (
                    event.created_at.isoformat()
                    if event.created_at else None
                ),
            }
            for event in events
        ],
    }


@router.get("/positions/exchange")
def get_exchange_positions(
    db: Session = Depends(get_db),
):

    records = (
        db.query(ExchangePosition)
        .order_by(
            ExchangePosition.symbol,
            ExchangePosition.direction,
        )
        .all()
    )

    return {
        "count": len(records),
        "positions": [
            {
                "symbol": item.symbol,
                "direction": item.direction,
                "quantity": item.exchange_quantity,
                "entry_price": item.entry_price,
                "mark_price": item.mark_price,
                "unrealized_pnl": item.unrealized_pnl,
                "last_synced_at": (
                    item.last_synced_at.isoformat()
                    if item.last_synced_at else None
                ),
            }
            for item in records
        ],
    }


@router.post("/positions/reconcile")
def reconcile_positions():

    try:
        return reconciliation_manager.sync_positions()

    except Exception as error:

        logger.exception(
            "Position reconciliation API failed."
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Position synchronization failed. "
                "Check server logs and Binance Testnet connection."
            ),
        ) from error


@router.post("/orders/synchronize")
def synchronize_orders():

    try:
        results = order_status_manager.sync_pending_orders()

        return {
            "success": True,
            "synchronized_orders": len(results),
            "orders": results,
        }

    except Exception as error:

        logger.exception(
            "Order synchronization API failed."
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Order synchronization failed. "
                "Check server logs and Binance Testnet order history."
            ),
        ) from error


@router.get("/reentries")
def get_reentries(
    status: str = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):

    query = db.query(ReentryRecord)

    if status:

        allowed_statuses = {
            "WAITING",
            "PROCESSING",
            "TRIGGERED",
            "ORDER_UNCONFIRMED",
        }

        normalized_status = status.strip().upper()

        if normalized_status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail="Invalid re-entry status.",
            )

        query = query.filter(
            ReentryRecord.status == normalized_status
        )

    records = (
        query.order_by(ReentryRecord.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(records),
        "reentries": [
            {
                "id": item.id,
                "cycle_id": item.cycle_id,
                "new_cycle_id": item.new_cycle_id,
                "symbol": item.symbol,
                "direction": item.direction,
                "reference_close_price": (
                    item.reference_close_price
                ),
                "trigger_price": item.trigger_price,
                "status": item.status,
                "created_at": (
                    item.created_at.isoformat()
                    if item.created_at else None
                ),
                "triggered_at": (
                    item.triggered_at.isoformat()
                    if item.triggered_at else None
                ),
            }
            for item in records
        ],
    }
