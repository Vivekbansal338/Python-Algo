"""
================================================================================
V4 ORDER MANAGER (PAPER TRADING)
================================================================================
Abstracts Zerodha API interaction.
Currently strictly enforces PAPER TRADING mode.
Simulates:
- Order Placement (Limit/SL-M)
- Fills (Instant for Paper)
- Cancellations

Author: Sector Analysis System
Version: 4.0.0
================================================================================
"""

import logging
import uuid
from typing import Dict, Optional, List
from datetime import datetime

from core_v4 import config_v4 as config
from core_v4.data_v4 import data_manager

logger = logging.getLogger("OrdersV4")


class OrderManager:
    def __init__(self):
        self.is_paper = config.IS_PAPER_TRADING
        self.paper_orders: Dict[str, Dict] = {}
        self.paper_positions: Dict[str, Dict] = {}
        
        if not self.is_paper:
            logger.critical("V4 IS STRICTLY PAPER TRADING. LIVE MODE NOT SUPPORTED.")
            raise RuntimeError("Live Mode Disabled in V4")

    # ══════════════════════════════════════════════════════════════════════════
    # ORDER PLACEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def place_entry_order(self, symbol: str, direction: str, qty: int, price: float, tag: str, sector: str = "UNKNOWN") -> Optional[str]:
        """
        Place LIMIT Entry Order.
        In Paper Mode: Simulates instant fill if price is reasonable.
        """
        order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
        
        logger.info(f"[{'PAPER' if self.is_paper else 'LIVE'}] ENTRY {direction} {symbol} {qty} @ {price}")
        
        if self.is_paper:
            # Simulate Fill
            self.paper_orders[order_id] = {
                "order_id": order_id,
                "symbol": symbol,
                "direction": direction,
                "qty": qty,
                "price": price,
                "status": "COMPLETE",
                "tag": tag,
                "timestamp": datetime.now()
            }
            
            # Update Simulated Position
            self._update_paper_position(symbol, direction, qty, price, sector)
            return order_id
            
        return None

    def place_stop_loss(self, symbol: str, direction: str, qty: int, trigger_price: float, tag: str) -> Optional[str]:
        """
        Place SL-M Order.
        In Paper Mode: Stores as a 'Pending' stop order.
        """
        order_id = f"SL_{uuid.uuid4().hex[:8].upper()}"
        
        # Stop direction is opposite to entry
        stop_dir = "SELL" if direction == "LONG" else "BUY"
        
        logger.info(f"[{'PAPER' if self.is_paper else 'LIVE'}] SL-M {stop_dir} {symbol} {qty} @ {trigger_price}")
        
        if self.is_paper:
            self.paper_orders[order_id] = {
                "order_id": order_id,
                "symbol": symbol,
                "direction": stop_dir,
                "qty": qty,
                "trigger_price": trigger_price,
                "status": "TRIGGER PENDING",
                "tag": tag,
                "timestamp": datetime.now()
            }
            return order_id
            
        return None

    def modify_order(self, order_id: str, new_price: float = None, new_trigger: float = None) -> bool:
        """Modify open order (Entry or SL)."""
        if self.is_paper:
            if order_id in self.paper_orders:
                order = self.paper_orders[order_id]
                if new_price: order["price"] = new_price
                if new_trigger: order["trigger_price"] = new_trigger
                logger.info(f"[PAPER] MODIFIED {order_id} -> P: {new_price} T: {new_trigger}")
                return True
            return False
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel order."""
        if self.is_paper:
            if order_id in self.paper_orders:
                self.paper_orders[order_id]["status"] = "CANCELLED"
                logger.info(f"[PAPER] CANCELLED {order_id}")
                return True
            return False
        return False

    def close_position(self, symbol: str, qty: int, tag: str) -> Optional[str]:
        """Market Exit."""
        if symbol not in self.paper_positions:
            logger.warning(f"Attempt to close non-existent position: {symbol}")
            return None
            
        pos = self.paper_positions[symbol]
        direction = "SELL" if pos["qty"] > 0 else "BUY"
        
        # Get current LTP for simulation
        quote = data_manager.get_quote([symbol])
        key = f"NSE:{symbol}"
        exit_price = quote[key]['last_price'] if quote and key in quote else pos["avg_price"] # Fallback
        
        order_id = f"EXIT_{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"[PAPER] EXIT {symbol} {qty} @ {exit_price}")
        
        # Update Position
        self._update_paper_position(symbol, direction, qty, exit_price)
        return order_id

    # ══════════════════════════════════════════════════════════════════════════
    # PAPER ENGINE INTERNALS
    # ══════════════════════════════════════════════════════════════════════════

    def _update_paper_position(self, symbol: str, direction: str, qty: int, price: float, sector: str = "UNKNOWN"):
        """Internal accounting for paper trades."""
        if symbol not in self.paper_positions:
            self.paper_positions[symbol] = {"qty": 0, "avg_price": 0.0, "pnl": 0.0, "sector": sector}
            
        pos = self.paper_positions[symbol]
        
        signed_qty = qty if direction == "LONG" or direction == "BUY" else -qty
        
        # If closing (reducing size)
        if (pos["qty"] > 0 and signed_qty < 0) or (pos["qty"] < 0 and signed_qty > 0):
            # Calculate PnL on closed portion
            closed_qty = abs(signed_qty)
            if pos["qty"] > 0: # Long Close
                trade_pnl = (price - pos["avg_price"]) * closed_qty
            else: # Short Close
                trade_pnl = (pos["avg_price"] - price) * closed_qty
            
            pos["pnl"] += trade_pnl
            pos["qty"] += signed_qty
            
            if pos["qty"] == 0:
                del self.paper_positions[symbol]
                
        else:
            # Increasing size (Weighted Average Price)
            new_total_qty = pos["qty"] + signed_qty
            total_cost = (abs(pos["qty"]) * pos["avg_price"]) + (abs(signed_qty) * price)
            pos["avg_price"] = total_cost / abs(new_total_qty)
            pos["qty"] = new_total_qty

    def get_positions(self) -> List[Dict]:
        """Return standardized position list."""
        if self.is_paper:
            return [
                {
                    "symbol": sym,
                    "qty": p["qty"],
                    "entry_price": p["avg_price"],
                    "pnl": p["pnl"], # Realized PnL here (Unrealized calc needed in lifecycle)
                    "sector": p.get("sector", "UNKNOWN")
                }
                for sym, p in self.paper_positions.items()
            ]
        return []
