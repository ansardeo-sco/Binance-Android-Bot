import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from binance_client import BinanceFuturesClient

class TradingEngine:
    def __init__(self):
        self.client = BinanceFuturesClient()

    async def evaluate_cycle_triggers(self, cycle_id: str, current_price: float):
        """
        Evaluate price movement against initial entry price for 6%, 7%, and 9% triggers.
        """
        db: Session = SessionLocal()
        try:
            # Get active cycle
            cycle = db.query(models.TradingCycle).filter(
                models.TradingCycle.cycle_id == cycle_id,
                models.TradingCycle.status == "ACTIVE"
            ).first()
            
            if not cycle:
                return

            # Get initial entry price from cycle entries
            initial_entry = db.query(models.CycleEntry).filter(
                models.CycleEntry.cycle_id == cycle_id,
                models.CycleEntry.entry_type == "INITIAL"
            ).first()

            if not initial_entry:
                return

            entry_price = initial_entry.entry_price
            direction = cycle.direction.upper()

            # Calculate price movement percentage
            if direction == "LONG":
                price_change_pct = ((current_price - entry_price) / entry_price) * 100
                # Adverse movement is negative for long
                adverse_move = -price_change_pct
            else:  # SHORT
                price_change_pct = ((entry_price - current_price) / entry_price) * 100
                # Adverse movement is negative for short
                adverse_move = -price_change_pct

            # Check Triggers if adverse movement occurs
            if adverse_move >= cycle.warning_percent:
                print(f"⚠️ WARNING TRIGGER ({cycle.warning_percent}%): Cycle {cycle_id} at price {current_price}")
                # Here warning notification will be triggered

            if adverse_move >= cycle.opposite_percent:
                print(f"🔄 OPPOSITE POSITION TRIGGER ({cycle.opposite_percent}%): Cycle {cycle_id}")
                # Logic for opening opposite position will execute here

            if adverse_move >= cycle.averaging_percent:
                print(f"📈 AVERAGING TRIGGER ({cycle.averaging_percent}%): Cycle {cycle_id}")
                # Logic for averaging entry will execute here

        except Exception as e:
            print(f"Error evaluating triggers for cycle {cycle_id}: {e}")
        finally:
            db.close()

    async def monitor_market(self):
        """
        Continuous monitoring loop for active trading cycles.
        """
        while True:
            db: Session = SessionLocal()
            try:
                active_cycles = db.query(models.TradingCycle).filter(models.TradingCycle.status == "ACTIVE").all()
                for cycle in active_cycles:
                    current_price = await self.client.get_market_price(cycle.symbol)
                    if current_price > 0:
                        await self.evaluate_cycle_triggers(cycle.cycle_id, current_price)
            except Exception as e:
                print(f"Error in market monitoring loop: {e}")
            finally:
                db.close()
            
            # Check market every 10 seconds
            await asyncio.sleep(10)

engine = TradingEngine()
