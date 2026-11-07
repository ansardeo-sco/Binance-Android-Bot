
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Notification,
    BotEvent,
    ExchangePosition,
    CycleOrder,
    ReentryRecord,
)

from notification_manager import notification_manager
from order_status_manager import order_status_manager
from reconciliation_manager import reconciliation_manager


router = APIRouter(
    prefix="/api/v1",
    tags=["Bot Management"],
)


@router.get("/notifications")
def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))

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
            detail="Notification not found",
        )

    return {"success": True}


@router.get("/events")
def get_bot_events(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))

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
        .order_by(ExchangePosition.symbol)
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
        raise HTTPException(
            status_code=503,
            detail=(
                "Position synchronization failed: "
                f"{error}"
            ),
        )


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
        raise HTTPException(
            status_code=503,
            detail=(
                "Order synchronization failed: "
                f"{error}"
            ),
        )


@router.get("/reentries")
def get_reentries(
    status: str = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))

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
