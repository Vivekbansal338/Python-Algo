"""
================================================================================
V4 LIFECYCLE MANAGER
================================================================================
Manages the State Machine for every trade.
Transitions: PENDING -> ACTIVE -> PARTIAL -> CLOSED

Features:
- Two-Stage Exit (50% @ 1.5R)
- Chandelier Trailing
- Stop Loss Management
- 15:05 Force Exit Logic

Author: Sector Analysis System
Version: 4.0.0
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime, time, timedelta

from core_v4 import config_v4 as config
from core_v4.data_v4 import data_manager
from execution_v4.orders_v4 import OrderManager
from analysis_v4.indicators_v4 import calculate_atr

logger = logging.getLogger("LifecycleV4")


@dataclass
class Trade:
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


class LifecycleManager:
    def __init__(self, order_manager: OrderManager):
        self.orders = order_manager
        self.trades: Dict[str, Trade] = {}
        
    # ══════════════════════════════════════════════════════════════════════════
    # TRADE INITIATION
    # ══════════════════════════════════════════════════════════════════════════

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
        # 1. Place Entry
        order_id = self.orders.place_entry_order(symbol, direction, qty, entry_price, "V4_ENTRY", sector=sector)
        if not order_id:
            return None
            
        # 2. Calculate Targets
        risk = abs(entry_price - stop_price)
        target_1_price = entry_price + (risk * 1.5) if direction == "LONG" else entry_price - (risk * 1.5)
        
        # 3. Register Trade
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
        
        # 4. Place Stop Order
        self.orders.place_stop_loss(symbol, direction, qty, stop_price, f"{trade_id}_SL")
        
        logger.info(f"Trade Initiated: {trade_id} {symbol} {direction} Target1: {target_1_price:.2f}")
        return trade_id

    # ══════════════════════════════════════════════════════════════════════════
    # MONITORING & UPDATES
    # ══════════════════════════════════════════════════════════════════════════

    def update_trades(self, market_data: Dict[str, Dict]):
        """
        Main Loop Processor.
        Updates state for all active trades based on current price.
        """
        trades_to_close = []
        
        for trade_id, trade in self.trades.items():
            if trade.stage == "CLOSED": continue
            
            # Get Current Price
            key = f"NSE:{trade.symbol}"
            if key not in market_data: continue
            
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
                
                # Close 50%
                partial_qty = max(1, int(trade.qty * 0.5))
                self.orders.close_position(trade.symbol, partial_qty, f"{trade.id}_T1")
                trade.qty -= partial_qty
                
                # Move Stop to Breakeven
                trade.current_stop = trade.entry_price
                trade.stage = "PARTIAL"
                
                # Update Stop Order
                # (In simulated V4, we just log this update, order manager handles logic)
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
        atr_buffer = trade.atr_at_entry * 3.0
        now = datetime.now()

        # 1. Update Lookback Extreme if needed (Rolling window)
        if (now - trade.last_anchor_update).total_seconds() > 60 or trade.cached_lookback_extreme == 0:
            try:
                # Fetch 2 hours of 5m data to ensure we get 10 valid bars
                token = data_manager.get_token(f"NSE:{trade.symbol}")
                if token:
                    hist = data_manager.get_historical(
                        token, 
                        now - timedelta(hours=2), 
                        now, 
                        "5minute"
                    )
                    if hist and len(hist) >= 10:
                        last_10 = hist[-10:]
                        if trade.direction == "LONG":
                            trade.cached_lookback_extreme = max(d['high'] for d in last_10)
                        else:
                            trade.cached_lookback_extreme = min(d['low'] for d in last_10)
                        
                        trade.last_anchor_update = now
            except Exception as e:
                logger.warning(f"Chandelier lookback fetch failed for {trade.symbol}: {e}")

        # 2. Final Anchor (Lookback Extreme vs Current Trade High/Low)
        # We take the best of both to ensure we don't trail 'backwards'
        anchor = trade.cached_lookback_extreme
        
        # Fallback to Life-of-Trade extremes if lookback fetch failed
        if anchor == 0:
            anchor = trade.highest_price if trade.direction == "LONG" else trade.lowest_price

        if trade.direction == "LONG":
            # Chandelier Anchor = Max of (10-bar High, Current Session High)
            final_anchor = max(anchor, trade.highest_price)
            return final_anchor - atr_buffer
        else:
            # Chandelier Anchor = Min of (10-bar Low, Current Session Low)
            final_anchor = min(anchor, trade.lowest_price)
            return final_anchor + atr_buffer

    # ══════════════════════════════════════════════════════════════════════════
    # SYSTEM EVENTS
    # ══════════════════════════════════════════════════════════════════════════

    def force_exit_all(self):
        """Execute 15:05 Force Exit."""
        logger.warning("EXECUTING FORCE EXIT (15:05)")
        for trade_id, trade in self.trades.items():
            if trade.stage != "CLOSED":
                self.orders.close_position(trade.symbol, trade.qty, "FORCE_EXIT")
                trade.stage = "CLOSED"
