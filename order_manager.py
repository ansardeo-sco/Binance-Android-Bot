import logging
import uuid

from sqlalchemy.orm import Session

from config import settings
from binance_client import binance_client
from models import CycleEntry, CycleOrder
from risk_manager import risk_manager


logger = logging.getLogger(__name__)


class OrderManager:

    def place_initial_entry(
        self,
        db: Session,
        cycle,
    ):

        validated = risk_manager.validate_initial_entry(
            symbol=cycle.symbol,
            direction=cycle.direction,
            margin=cycle.initial_margin,
            leverage=cycle.leverage,
        )

        if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
            raise RuntimeError(
                "Binance API credentials are missing."
            )

        exchange = binance_client.exchange
        symbol = validated["symbol"]

        binance_client._load_markets_sync()

        market_price = binance_client._fetch_mark_price_sync(
            symbol
        )

        if not market_price or market_price <= 0:
            raise ValueError("Invalid market price.")

        market = exchange.market(symbol)

        raw_quantity = (
            validated["margin"] * validated["leverage"]
        ) / market_price

        quantity = float(
            exchange.amount_to_precision(
                symbol,
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

        # Exchange کو درخواست بھیجنے سے پہلے ریکارڈ محفوظ کریں۔
        db.commit()

        try:

            exchange.set_margin_mode(
                "isolated",
                symbol,
            )

            exchange.set_leverage(
                validated["leverage"],
                symbol,
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
                symbol=symbol,
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

                order_record.exchange_order_id = str(
                    order_id
                )

                entry.exchange_order_id = str(
                    order_id
                )

                try:

                    confirmed = exchange.fetch_order(
                        order_id,
                        symbol,
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
                if average_price
                else None
            )

            order_record.filled_quantity = filled

            order_record.average_fill_price = (
                float(average_price)
                if average_price
                else None
            )

            exchange_status = str(
                result.get("status") or "open"
            ).lower()

            if exchange_status == "closed":

                entry.status = "FILLED"
                order_record.status = "FILLED"

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

            # درخواست Exchange تک پہنچ چکی ہو سکتی ہے۔
            # اس لیے اسے ERROR نہیں بلکہ UNKNOWN رکھیں۔
            # دوبارہ آرڈر لگانے سے پہلے Exchange history چیک کرنا ضروری ہے۔

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
