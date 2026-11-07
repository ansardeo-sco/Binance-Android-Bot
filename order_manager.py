
import logging
import uuid

from sqlalchemy.orm import Session

from config import settings
from binance_client import binance_client
from models import CycleEntry, CycleOrder
from risk_manager import risk_manager


logger = logging.getLogger(__name__)

EPSILON = 0.00000001


class OrderManager:

    def place_initial_entry(self, db: Session, cycle):

        validated = risk_manager.validate_initial_entry(
            symbol=cycle.symbol,
            direction=cycle.direction,
            margin=cycle.initial_margin,
            leverage=cycle.leverage,
        )

        if (
            not settings.BINANCE_API_KEY
            or not settings.BINANCE_API_SECRET
        ):
            raise RuntimeError(
                "Binance API credentials are missing."
            )

        exchange = binance_client.exchange
        symbol = validated["symbol"]

        binance_client._load_markets_sync()

        exchange_symbol = binance_client.get_exchange_symbol(
            symbol
        )

        market_price = binance_client._fetch_mark_price_sync(
            symbol
        )

        if not market_price or market_price <= 0:
            raise ValueError("Invalid market price.")

        market = exchange.market(exchange_symbol)

        raw_quantity = (
            validated["margin"] * validated["leverage"]
        ) / market_price

        quantity = float(
            exchange.amount_to_precision(
                exchange_symbol,
                raw_quantity,
            )
        )

        if quantity <= 0:
            raise ValueError(
                "Calculated order quantity is zero."
            )

        min_amount = (
            (market.get("limits") or {})
            .get("amount", {})
            .get("min")
        )

        if (
            min_amount is not None
            and quantity < float(min_amount)
        ):
            raise ValueError(
                f"Order quantity {quantity} is below "
                f"minimum quantity {min_amount}."
            )

        client_order_id = (
            "bot_" + uuid.uuid4().hex[:24]
        )

        entry = CycleEntry(
            cycle_id=cycle.id,
            symbol=symbol,
            direction=validated["direction"],
            entry_type="INITIAL",
            status="PENDING",
            requested_margin=validated["margin"],
            leverage=validated["leverage"],
            requested_quantity=quantity,
            filled_quantity=0.0,
            remaining_quantity=0.0,
            stop_loss_percent=cycle.sl_percent,
            client_order_id=client_order_id,
        )

        order_record = CycleOrder(
            cycle_id=cycle.id,
            entry_id=None,
            symbol=symbol,
            order_type="MARKET",
            side=(
                "buy"
                if validated["direction"] == "LONG"
                else "sell"
            ),
            status="PENDING",
            requested_quantity=quantity,
            filled_quantity=0.0,
            client_order_id=client_order_id,
            reduce_position=False,
        )

        db.add(entry)
        db.flush()

        order_record.entry_id = entry.id

        db.add(order_record)

        # Exchange request سے پہلے دونوں ریکارڈ محفوظ کریں۔
        db.commit()

        try:

            exchange.set_margin_mode(
                "isolated",
                exchange_symbol,
            )

            exchange.set_leverage(
                validated["leverage"],
                exchange_symbol,
            )

            side = (
                "buy"
                if validated["direction"] == "LONG"
                else "sell"
            )

            params = {
                "positionSide": validated["direction"],
                "newClientOrderId": client_order_id,
            }

            result = exchange.create_order(
                symbol=exchange_symbol,
                type="market",
                side=side,
                amount=quantity,
                params=params,
            )

            order_id = result.get("id")

            filled = float(
                result.get("filled") or 0
            )

            average_price = result.get("average")

            if order_id:

                order_record.exchange_order_id = str(order_id)
                entry.exchange_order_id = str(order_id)

                try:

                    confirmed = exchange.fetch_order(
                        order_id,
                        exchange_symbol,
                    )

                    filled = float(
                        confirmed.get("filled") or filled
                    )

                    average_price = (
                        confirmed.get("average")
                        or average_price
                    )

                    result = confirmed

                except Exception as fetch_error:

                    logger.warning(
                        "Order placed but confirmation "
                        "fetch failed: %s",
                        fetch_error,
                    )

            entry.filled_quantity = filled
            entry.remaining_quantity = filled

            entry.entry_price = (
                float(average_price)
                if average_price is not None
                else None
            )

            order_record.filled_quantity = filled

            order_record.average_fill_price = (
                float(average_price)
                if average_price is not None
                else None
            )

            exchange_status = str(
                result.get("status") or "open"
            ).lower()

            is_terminal = exchange_status in (
                "closed",
                "canceled",
                "cancelled",
                "expired",
                "rejected",
            )

            is_fully_filled = (
                quantity > 0
                and filled + EPSILON >= quantity
            )

            if is_terminal and is_fully_filled:

                entry.status = "FILLED"
                order_record.status = "FILLED"

            elif is_terminal and filled > 0:

                entry.status = "PARTIALLY_FILLED"
                order_record.status = "CANCELLED_PARTIAL"

            elif is_terminal:

                entry.status = "CANCELLED"
                order_record.status = "CANCELLED"

            elif filled > 0:

                entry.status = "PARTIALLY_FILLED"
                order_record.status = "PARTIALLY_FILLED"

            else:

                entry.status = "PENDING"
                order_record.status = "PENDING"

            db.commit()

            return {
                "success": True,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "direction": validated["direction"],
                "requested_quantity": quantity,
                "filled_quantity": filled,
                "average_price": average_price,
                "order_status": order_record.status,
                "message": (
                    "Testnet order submitted. "
                    "Exchange confirmation must be monitored."
                ),
            }

        except Exception as error:

            db.rollback()

            entry = (
                db.query(CycleEntry)
                .filter(
                    CycleEntry.client_order_id
                    == client_order_id
                )
                .first()
            )

            order_record = (
                db.query(CycleOrder)
                .filter(
                    CycleOrder.client_order_id
                    == client_order_id
                )
                .first()
            )

            if entry:
                entry.status = "UNKNOWN"

            if order_record:
                order_record.status = "UNKNOWN"
                order_record.error_message = str(error)

            db.commit()

            logger.exception(
                "Initial order could not be confirmed."
            )

            raise RuntimeError(
                "Initial order status is UNKNOWN. "
                "Check Binance Testnet order history "
                "before trying again. "
                f"Details: {error}"
            ) from error


order_manager = OrderManager()
