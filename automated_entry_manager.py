
import logging

from config import settings
from binance_client import binance_client
from models import CycleEntry, CycleOrder

logger = logging.getLogger(__name__)

EPSILON = 0.00000001


class AutomatedEntryManager:

    @staticmethod
    def _set_isolated_margin(exchange, symbol):
        try:
            exchange.set_margin_mode("isolated", symbol)
        except Exception as error:
            message = str(error).lower()

            # Binance error -4046 means the margin mode is already isolated.
            if "-4046" in message or "no need to change margin type" in message:
                return

            raise

    def place_entry(self, db, cycle, entry_type, margin):

        if not settings.BINANCE_USE_TESTNET:
            raise RuntimeError(
                "Automated entries are restricted to Testnet."
            )

        settings.validate_trading_mode()

        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            raise RuntimeError("Binance API credentials are missing.")

        if cycle.status != "ACTIVE":
            raise RuntimeError("Entries can only be placed in an ACTIVE cycle.")

        if entry_type not in ("AVERAGING", "OPPOSITE"):
            raise ValueError("Invalid automated entry type.")

        if cycle.direction not in ("LONG", "SHORT"):
            raise ValueError("Invalid cycle direction.")

        margin = float(margin or 0)

        if margin < settings.MIN_MARGIN_USDT:
            raise ValueError("Margin is below the minimum limit.")

        if margin > settings.MAX_MARGIN_USDT:
            raise ValueError("Margin exceeds the maximum limit.")

        existing = (
            db.query(CycleEntry)
            .filter(
                CycleEntry.cycle_id == cycle.id,
                CycleEntry.entry_type == entry_type,
            )
            .first()
        )

        if existing:
            raise RuntimeError(
                f"{entry_type} entry already exists for this cycle. "
                "Check its exchange status before taking further action."
            )

        exchange = binance_client.exchange
        symbol = cycle.symbol

        binance_client._load_markets_sync()
        market_price = binance_client._fetch_mark_price_sync(symbol)

        if market_price <= 0:
            raise ValueError("Invalid market price.")

        leverage = int(cycle.leverage)

        if leverage < 1 or leverage > settings.MAX_LEVERAGE:
            raise ValueError("Invalid leverage.")

        self._set_isolated_margin(exchange, symbol)
        exchange.set_leverage(leverage, symbol)

        raw_quantity = (margin * leverage) / market_price

        quantity = float(
            exchange.amount_to_precision(symbol, raw_quantity)
        )

        if quantity <= 0:
            raise ValueError("Calculated quantity is zero.")

        market = exchange.market(symbol)
        limits = market.get("limits") or {}

        min_amount = (limits.get("amount") or {}).get("min")
        min_cost = (limits.get("cost") or {}).get("min")

        if min_amount is not None and quantity < float(min_amount):
            raise ValueError("Quantity is below exchange minimum.")

        estimated_cost = quantity * market_price

        if min_cost is not None and estimated_cost < float(min_cost):
            raise ValueError(
                "Order value is below the exchange minimum cost."
            )

        suffix = "A" if entry_type == "AVERAGING" else "O"
        client_order_id = f"bot{cycle.id}{suffix}"

        duplicate_order = (
            db.query(CycleOrder)
            .filter(CycleOrder.client_order_id == client_order_id)
            .first()
        )

        if duplicate_order:
            raise RuntimeError(
                "This automated order ID already exists. "
                "Exchange reconciliation is required."
            )

        side = "buy" if cycle.direction == "LONG" else "sell"

        entry = CycleEntry(
            cycle_id=cycle.id,
            symbol=symbol,
            direction=cycle.direction,
            entry_type=entry_type,
            status="PENDING",
            requested_margin=margin,
            leverage=leverage,
            requested_quantity=quantity,
            filled_quantity=0.0,
            remaining_quantity=0.0,
            stop_loss_percent=cycle.sl_percent,
            client_order_id=client_order_id,
        )

        order = CycleOrder(
            cycle_id=cycle.id,
            entry_id=None,
            symbol=symbol,
            order_type="MARKET",
            side=side,
            status="PENDING",
            requested_quantity=quantity,
            filled_quantity=0.0,
            client_order_id=client_order_id,
            reduce_position=False,
        )

        db.add(entry)
        db.flush()

        order.entry_id = entry.id
        db.add(order)

        # Save the local record before contacting Binance.
        db.commit()

        try:
            result = exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=quantity,
                params={
                    "positionSide": cycle.direction,
                    "newClientOrderId": client_order_id,
                },
            )

            order_id = result.get("id")

            if not order_id:
                raise RuntimeError(
                    "Exchange did not return an order ID."
                )

            order.exchange_order_id = str(order_id)
            entry.exchange_order_id = str(order_id)
            db.commit()

            confirmed = exchange.fetch_order(order_id, symbol)

            filled = float(confirmed.get("filled") or 0)
            average = confirmed.get("average")

            order.filled_quantity = filled
            order.average_fill_price = (
                float(average) if average is not None else None
            )

            entry.filled_quantity = filled
            entry.remaining_quantity = filled
            entry.entry_price = (
                float(average) if average is not None else None
            )

            status = str(
                confirmed.get("status") or "open"
            ).lower()

            is_terminal = status in (
                "closed",
                "canceled",
                "cancelled",
                "expired",
                "rejected",
            )

            is_fully_filled = (
                quantity > 0 and filled + EPSILON >= quantity
            )

            if is_terminal and is_fully_filled:
                order.status = "FILLED"
                entry.status = "FILLED"

            elif is_terminal and filled > 0:
                order.status = "CANCELLED_PARTIAL"
                entry.status = "PARTIALLY_FILLED"

            elif is_terminal:
                order.status = "CANCELLED"
                entry.status = "CANCELLED"

            elif filled > 0:
                order.status = "PARTIALLY_FILLED"
                entry.status = "PARTIALLY_FILLED"

            else:
                order.status = "PENDING"
                entry.status = "PENDING"

            db.commit()

            return {
                "success": True,
                "entry_id": entry.id,
                "order_id": order_id,
                "entry_type": entry_type,
                "filled_quantity": filled,
                "average_price": average,
                "status": order.status,
            }

        except Exception as error:
            db.rollback()

            saved_entry = (
                db.query(CycleEntry)
                .filter(
                    CycleEntry.client_order_id == client_order_id
                )
                .first()
            )

            saved_order = (
                db.query(CycleOrder)
                .filter(
                    CycleOrder.client_order_id == client_order_id
                )
                .first()
            )

            if saved_entry:
                saved_entry.status = "UNKNOWN"

            if saved_order:
                saved_order.status = "UNKNOWN"
                saved_order.error_message = str(error)

            db.commit()

            logger.exception(
                "Automated entry could not be confirmed."
            )

            raise RuntimeError(
                "Automated order status is UNKNOWN. "
                "Do not retry before Binance Testnet reconciliation."
            ) from error


automated_entry_manager = AutomatedEntryManager()
