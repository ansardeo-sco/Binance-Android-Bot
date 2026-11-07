import logging
import uuid
import threading

from config import settings
from binance_client import binance_client
from models import CycleEntry, CycleOrder


logger = logging.getLogger(__name__)


class CloseOrderManager:

    def __init__(self):
        self._lock = threading.RLock()

    def close_entry(self, db, entry_id: int, reason="MANUAL_CLOSE"):

        with self._lock:

            if not settings.BINANCE_USE_TESTNET:
                raise RuntimeError("Closing orders are restricted to Testnet.")

            settings.validate_trading_mode()

            if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
                raise RuntimeError("Binance API credentials are missing.")

            entry = (
                db.query(CycleEntry)
                .filter(CycleEntry.id == entry_id)
                .with_for_update()
                .first()
            )

            if not entry:
                raise ValueError("Entry not found.")

            remaining = float(entry.remaining_quantity or 0)

            if remaining <= 0:
                return {
                    "success": True,
                    "message": "Entry is already closed.",
                    "entry_id": entry.id,
                }

            pending_close = (
                db.query(CycleOrder)
                .filter(
                    CycleOrder.entry_id == entry.id,
                    CycleOrder.reduce_position.is_(True),
                    CycleOrder.status.in_([
                        "PENDING",
                        "PARTIALLY_FILLED",
                        "UNKNOWN",
                    ]),
                )
                .first()
            )

            if pending_close:
                return {
                    "success": False,
                    "message": "A closing order is already pending.",
                    "entry_id": entry.id,
                    "order_id": pending_close.id,
                }

            exchange = binance_client.exchange

            positions = exchange.fetch_positions()

            exchange_quantity = 0.0

            for position in positions:
                info = position.get("info") or {}

                exchange_symbol = str(
                    info.get("symbol") or ""
                ).upper()

                position_side = str(
                    info.get("positionSide")
                    or position.get("side")
                    or ""
                ).upper()

                if (
                    exchange_symbol == entry.symbol.upper()
                    and position_side == entry.direction.upper()
                ):
                    raw_amount = info.get("positionAmt")

                    if raw_amount is not None:
                        exchange_quantity = abs(float(raw_amount))
                    else:
                        exchange_quantity = abs(
                            float(position.get("contracts") or 0)
                        )

                    break

            if exchange_quantity <= 0:
                raise RuntimeError(
                    "No matching exchange position found. "
                    "Reconcile positions before closing."
                )

            close_quantity = min(remaining, exchange_quantity)

            close_quantity = float(
                exchange.amount_to_precision(
                    entry.symbol,
                    close_quantity,
                )
            )

            if close_quantity <= 0:
                raise ValueError("Closing quantity is zero.")

            client_order_id = "close_" + uuid.uuid4().hex[:24]

            close_side = (
                "sell" if entry.direction == "LONG" else "buy"
            )

            order_record = CycleOrder(
                cycle_id=entry.cycle_id,
                entry_id=entry.id,
                symbol=entry.symbol,
                order_type=f"{reason.upper()}_CLOSE",
                side=close_side,
                status="PENDING",
                requested_quantity=close_quantity,
                filled_quantity=0.0,
                client_order_id=client_order_id,
                reduce_position=True,
            )

            db.add(order_record)
            db.commit()
            db.refresh(order_record)

            try:
                result = exchange.create_order(
                    symbol=entry.symbol,
                    type="market",
                    side=close_side,
                    amount=close_quantity,
                    params={
                        "positionSide": entry.direction,
                        "newClientOrderId": client_order_id,
                    },
                )

                order_id = result.get("id")

                order_record.exchange_order_id = (
                    str(order_id) if order_id else None
                )

                # Filled quantity is updated only by order_status_manager.
                # This prevents the same fill being deducted twice.
                order_record.status = (
                    "PENDING" if order_id else "UNKNOWN"
                )

                if not order_id:
                    order_record.error_message = (
                        "Exchange response did not contain an order ID. "
                        "Manual exchange verification is required."
                    )

                db.commit()

                return {
                    "success": bool(order_id),
                    "entry_id": entry.id,
                    "order_id": order_record.id,
                    "exchange_order_id": order_id,
                    "reason": reason,
                    "requested_quantity": close_quantity,
                    "status": order_record.status,
                    "message": (
                        "Close order submitted. Fill confirmation is pending."
                        if order_id
                        else "Order response is uncertain. Do not retry."
                    ),
                }

            except Exception as error:
                db.rollback()

                saved_order = (
                    db.query(CycleOrder)
                    .filter(
                        CycleOrder.client_order_id == client_order_id
                    )
                    .first()
                )

                if saved_order:
                    saved_order.status = "UNKNOWN"
                    saved_order.error_message = str(error)
                    db.commit()

                logger.exception("Closing order confirmation failed.")

                raise RuntimeError(
                    "Closing order status is unknown. "
                    "Check Binance order history before any retry."
                ) from error


close_order_manager = CloseOrderManager()
