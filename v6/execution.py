"""
================================================================================
V6 EXECUTION MODULE
================================================================================
Complete trade execution layer: Orders, Lifecycle, and State Persistence.

MERGED FROM V5:
- execution_v5/orders_v5.py → OrderManager
- execution_v5/lifecycle_v5.py → LifecycleManager, Trade
- system_v5/state_v5.py → StateManager

Author: Sector Analysis System
Version: 6.0.0
================================================================================
"""

import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from v6 import config
from v6.data_engine import data_manager

logger = logging.getLogger("ExecutionV6")


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Trade:
    """Active trade state."""
    id: str
    symbol: str
    direction: str  # LONG/SHORT
    entry_price: float
    qty: int
    initial_stop: float
    current_stop: float
    target_1: float
    stage: str  # 'ACTIVE', 'PARTIAL', 'CLOSED'
    entry_time: datetime
    atr_at_entry: float
    highest_price: float  # For trailing
    lowest_price: float   # For trailing
    pnl: float = 0.0
    last_anchor_update: datetime = field(default_factory=datetime.now)
    cached_lookback_extreme: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# ORDER MANAGER (PAPER TRADING)
# ══════════════════════════════════════════════════════════════════════════════

class OrderManager:
    """
    Abstracts Zerodha API interaction.
    Currently strictly enforces PAPER TRADING mode.
    """
    
    def __init__(self):
        self.is_paper = config.IS_PAPER_TRADING
        self.paper_orders: Dict[str, Dict] = {}
        self.paper_positions: Dict[str, Dict] = {}
        
        if not self.is_paper:
            logger.critical("V6 IS STRICTLY PAPER TRADING. LIVE MODE NOT SUPPORTED.")
            raise RuntimeError("Live Mode Disabled in V6")

    # --- ORDER PLACEMENT ---

    def place_entry_order(self, symbol: str, direction: str, qty: int, price: float, 
                          tag: str, sector: str = "UNKNOWN") -> Optional[str]:
        """
        Place LIMIT Entry Order.
        In Paper Mode: Simulates instant fill if price is reasonable.
        """
        order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
        
        logger.info(f"[{'PAPER' if self.is_paper else 'LIVE'}] ENTRY {direction} {symbol} {qty} @ {price}")
        
        if self.is_paper:
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
            self._update_paper_position(symbol, direction, qty, price, sector)
            return order_id
            
        return None

    def place_stop_loss(self, symbol: str, direction: str, qty: int, 
                        trigger_price: float, tag: str) -> Optional[str]:
        """
        Place SL-M Order.
        In Paper Mode: Stores as a 'Pending' stop order.
        """
        order_id = f"SL_{uuid.uuid4().hex[:8].upper()}"
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

    def modify_order(self, order_id: str, new_price: float = None, 
                     new_trigger: float = None) -> bool:
        """Modify open order (Entry or SL)."""
        if self.is_paper:
            if order_id in self.paper_orders:
                order = self.paper_orders[order_id]
                if new_price:
                    order["price"] = new_price
                if new_trigger:
                    order["trigger_price"] = new_trigger
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
        
        quote = data_manager.get_quote([symbol])
        key = f"NSE:{symbol}"
        exit_price = quote[key]['last_price'] if quote and key in quote else pos["avg_price"]
        
        order_id = f"EXIT_{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"[PAPER] EXIT {symbol} {qty} @ {exit_price}")
        
        self._update_paper_position(symbol, direction, qty, exit_price)
        return order_id

    # --- PAPER ENGINE INTERNALS ---

    def _update_paper_position(self, symbol: str, direction: str, qty: int, 
                                price: float, sector: str = "UNKNOWN"):
        """Internal accounting for paper trades."""
        if symbol not in self.paper_positions:
            self.paper_positions[symbol] = {"qty": 0, "avg_price": 0.0, "pnl": 0.0, "sector": sector}
            
        pos = self.paper_positions[symbol]
        signed_qty = qty if direction in ("LONG", "BUY") else -qty
        
        # If closing (reducing size)
        if (pos["qty"] > 0 and signed_qty < 0) or (pos["qty"] < 0 and signed_qty > 0):
            closed_qty = abs(signed_qty)
            if pos["qty"] > 0:  # Long Close
                trade_pnl = (price - pos["avg_price"]) * closed_qty
            else:  # Short Close
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
                    "pnl": p["pnl"],
                    "sector": p.get("sector", "UNKNOWN")
                }
                for sym, p in self.paper_positions.items()
            ]
        return []


# ══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class LifecycleManager:
    """
    Manages the State Machine for every trade.
    Transitions: PENDING -> ACTIVE -> PARTIAL -> CLOSED
    
    Features:
    - Two-Stage Exit (50% @ 1.5R)
    - Chandelier Trailing
    - Stop Loss Management
    - 15:05 Force Exit Logic
    """
    
    def __init__(self, order_manager: OrderManager):
        self.orders = order_manager
        self.trades: Dict[str, Trade] = {}
        
    # --- TRADE INITIATION ---

    def initiate_trade(self, 
                       symbol: str, 
                       direction: str, 
                       qty: int, 
                       entry_price: float, 
                       stop_price: float, 
                       atr: float,
                       sector: str = "UNKNOWN") -> Optional[str]:
        """
        Start a new trade lifecycle.
        1. Place Entry Order
        2. Place Initial Stop Loss
        3. Register Trade
        """
        order_id = self.orders.place_entry_order(symbol, direction, qty, entry_price, "V6_ENTRY", sector=sector)
        if not order_id:
            return None
            
        # Calculate Targets
        risk = abs(entry_price - stop_price)
        t1_dist = risk * config.TARGET_1_MULT
        target_1_price = entry_price + t1_dist if direction == "LONG" else entry_price - t1_dist
        
        # Register Trade
        trade_id = f"TRD_{symbol}_{datetime.now().strftime('%H%M%S')}"
        trade = Trade(
            id=trade_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            qty=qty,
            initial_stop=stop_price,
            current_stop=stop_price,
            target_1=target_1_price,
            stage="ACTIVE",
            entry_time=datetime.now(),
            atr_at_entry=atr,
            highest_price=entry_price,
            lowest_price=entry_price
        )
        
        self.trades[trade_id] = trade
        
        # Place Stop Order
        self.orders.place_stop_loss(symbol, direction, qty, stop_price, f"{trade_id}_SL")
        
        logger.info(f"Trade Initiated: {trade_id} {symbol} {direction} Target1: {target_1_price:.2f}")
        return trade_id

    # --- MONITORING & UPDATES ---

    def update_trades(self, market_data: Dict[str, Dict]):
        """
        Main Loop Processor.
        Updates state for all active trades based on current price.
        """
        trades_to_close = []
        
        for trade_id, trade in self.trades.items():
            if trade.stage == "CLOSED":
                continue
            
            key = f"NSE:{trade.symbol}"
            if key not in market_data:
                continue
            
            ltp = market_data[key]['last_price']
            
            # Update High/Low
            trade.highest_price = max(trade.highest_price, ltp)
            trade.lowest_price = min(trade.lowest_price, ltp)
            
            # Check Exit Conditions
            closed = self._check_exits(trade, ltp)
            if closed:
                trades_to_close.append(trade_id)
                
        # Cleanup
        for tid in trades_to_close:
            self.trades[tid].stage = "CLOSED"

    def _check_exits(self, trade: Trade, ltp: float) -> bool:
        """
        Check Stop Loss, Target 1, and Trailing Stops.
        Returns True if trade is fully closed.
        """
        # 1. Stop Loss Hit?
        stop_hit = (trade.direction == "LONG" and ltp <= trade.current_stop) or \
                   (trade.direction == "SHORT" and ltp >= trade.current_stop)
                   
        if stop_hit:
            logger.info(f"STOP HIT: {trade.id} @ {ltp}")
            self.orders.close_position(trade.symbol, trade.qty, f"{trade.id}_STOP")
            return True

        # 2. Stage 1 Target (1.5R) Hit?
        if trade.stage == "ACTIVE":
            target_hit = (trade.direction == "LONG" and ltp >= trade.target_1) or \
                         (trade.direction == "SHORT" and ltp <= trade.target_1)
                         
            if target_hit:
                logger.info(f"TARGET 1 HIT: {trade.id} @ {ltp}")
                
                # Close Partial
                partial_qty = max(1, int(trade.qty * config.TARGET_1_EXIT_PCT))
                self.orders.close_position(trade.symbol, partial_qty, f"{trade.id}_T1")
                trade.qty -= partial_qty
                
                # Move Stop to Breakeven
                trade.current_stop = trade.entry_price
                trade.stage = "PARTIAL"
                
                logger.info(f"Stop moved to Breakeven: {trade.current_stop}")

        # 3. Trailing Stop (Chandelier) for Partial Trades
        if trade.stage == "PARTIAL":
            new_stop = self._calculate_chandelier(trade)
            
            # Only move stop in favor of trade
            if trade.direction == "LONG":
                if new_stop > trade.current_stop:
                    trade.current_stop = new_stop
                    logger.info(f"Trailing Stop Updated: {trade.id} -> {new_stop:.2f}")
            else:
                if new_stop < trade.current_stop:
                    trade.current_stop = new_stop
                    logger.info(f"Trailing Stop Updated: {trade.id} -> {new_stop:.2f}")

        return False

    def _calculate_chandelier(self, trade: Trade) -> float:
        """
        Calculate Chandelier Stop using a 10-bar 5-min lookback extreme.
        Refreshes every 60 seconds to save API calls.
        """
        atr_buffer = trade.atr_at_entry * config.CHANDELIER_ATR_MULT
        now = datetime.now()

        # Update Lookback Extreme if needed (Rolling window)
        if (now - trade.last_anchor_update).total_seconds() > 60 or trade.cached_lookback_extreme == 0:
            try:
                token = data_manager.get_token(f"NSE:{trade.symbol}")
                if token:
                    hist = data_manager.get_historical(
                        token, 
                        now - timedelta(hours=2), 
                        now, 
                        "5minute"
                    )
                    if hist and len(hist) >= config.CHANDELIER_LOOKBACK:
                        last_n = hist[-config.CHANDELIER_LOOKBACK:]
                        if trade.direction == "LONG":
                            trade.cached_lookback_extreme = max(d['high'] for d in last_n)
                        else:
                            trade.cached_lookback_extreme = min(d['low'] for d in last_n)
                        
                        trade.last_anchor_update = now
            except Exception as e:
                logger.warning(f"Chandelier lookback fetch failed for {trade.symbol}: {e}")

        # Final Anchor (Lookback Extreme vs Current Trade High/Low)
        anchor = trade.cached_lookback_extreme
        
        # Fallback to Life-of-Trade extremes
        if anchor == 0:
            anchor = trade.highest_price if trade.direction == "LONG" else trade.lowest_price

        if trade.direction == "LONG":
            final_anchor = max(anchor, trade.highest_price)
            return final_anchor - atr_buffer
        else:
            final_anchor = min(anchor, trade.lowest_price)
            return final_anchor + atr_buffer

    # --- SYSTEM EVENTS ---

    def force_exit_all(self):
        """Execute 15:05 Force Exit."""
        logger.warning("EXECUTING FORCE EXIT (15:05)")
        for trade_id, trade in self.trades.items():
            if trade.stage != "CLOSED":
                self.orders.close_position(trade.symbol, trade.qty, "FORCE_EXIT")
                trade.stage = "CLOSED"


# ══════════════════════════════════════════════════════════════════════════════
# STATE MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class StateManager:
    """
    Manages saving and loading of system state to survive restarts.
    Handles:
    - Active Trades
    - Daily Stats (PnL, High Watermark)
    - Orders (Paper)
    """
    
    def __init__(self):
        self.file_path = config.STATE_FILE
        self.state: Dict[str, Any] = {
            "last_updated": None,
            "daily_start_equity": 0.0,
            "daily_high_equity": 0.0,
            "trades": {},
            "paper_orders": {},
            "paper_positions": {}
        }

    def load_state(self) -> bool:
        """Load state from disk."""
        if not self.file_path.exists():
            logger.info("No state file found. Starting fresh.")
            return False

        try:
            with open(self.file_path, 'r') as f:
                raw_data = json.load(f)
                
            # Validate date (reset if new day)
            saved_date = raw_data.get("last_updated", "")[:10]
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            if saved_date != current_date:
                logger.info(f"State file is from {saved_date}. Resetting for new day {current_date}.")
                self._archive_old_state(raw_data)
                return False
                
            self.state = raw_data
            logger.info("State loaded successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return False

    def save_state(self, risk_manager, lifecycle_manager, order_manager):
        """Save current system components to disk."""
        try:
            # Serialize Trades
            serialized_trades = {}
            for tid, trade in lifecycle_manager.trades.items():
                t_dict = asdict(trade)
                t_dict['entry_time'] = t_dict['entry_time'].isoformat()
                if isinstance(t_dict.get('last_anchor_update'), datetime):
                    t_dict['last_anchor_update'] = t_dict['last_anchor_update'].isoformat()
                serialized_trades[tid] = t_dict

            # Serialize Orders/Positions (Paper)
            serialized_orders = {}
            for oid, order in order_manager.paper_orders.items():
                o_copy = order.copy()
                if isinstance(o_copy.get('timestamp'), datetime):
                    o_copy['timestamp'] = o_copy['timestamp'].isoformat()
                serialized_orders[oid] = o_copy

            current_equity = risk_manager.state.equity

            self.state = {
                "last_updated": datetime.now().isoformat(),
                "daily_start_equity": risk_manager.state.daily_start_equity,
                "daily_high_equity": max(self.state.get("daily_high_equity", 0), current_equity),
                "trades": serialized_trades,
                "paper_orders": serialized_orders,
                "paper_positions": order_manager.paper_positions
            }

            with open(self.file_path, 'w') as f:
                json.dump(self.state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def restore_system(self, risk_manager, lifecycle_manager, order_manager):
        """Restore system components from loaded state."""
        if not self.state.get("trades"):
            return

        # Restore Risk State
        risk_manager.state.daily_start_equity = self.state.get("daily_start_equity", 0.0)
        
        # Restore Orders/Positions
        order_manager.paper_positions = self.state.get("paper_positions", {})
        restored_orders = self.state.get("paper_orders", {})
        for oid, order in restored_orders.items():
            if 'timestamp' in order:
                order['timestamp'] = datetime.fromisoformat(order['timestamp'])
        order_manager.paper_orders = restored_orders

        # Restore Trades
        raw_trades = self.state.get("trades", {})
        for tid, t_data in raw_trades.items():
            t_data['entry_time'] = datetime.fromisoformat(t_data['entry_time'])
            
            if 'last_anchor_update' in t_data and isinstance(t_data['last_anchor_update'], str):
                t_data['last_anchor_update'] = datetime.fromisoformat(t_data['last_anchor_update'])
            
            trade = Trade(**t_data)
            lifecycle_manager.trades[tid] = trade
            
        logger.info(f"Restored {len(lifecycle_manager.trades)} trades and {len(order_manager.paper_positions)} positions.")

    def _archive_old_state(self, old_state):
        """Archive old state file."""
        date_str = old_state.get("last_updated", "unknown")[:10]
        archive_path = config.DATA_DIR / f"state_v6_{date_str}.json"
        try:
            with open(archive_path, 'w') as f:
                json.dump(old_state, f, indent=2)
        except Exception:
            pass
