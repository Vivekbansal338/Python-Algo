"""
================================================================================
V5 SECTOR BACKTEST ENGINE
================================================================================
High-fidelity backtesting engine aligned with V5 production code (main_v5.py).

V5 KEY FIXES IMPLEMENTED:
1. Percentage Calculation: Uses Previous Close as anchor instead of Today's Open.
   This aligns with broker terminals and captures gap moves accurately.

2. Removed Redundant 15-min Logic: System processes every 5-minute candle.
   Sector ranks update continuously (matching WebSocket behavior in production).

3. RVOL Fresh Data: Uses actual 5-minute candles for RVOL calculation.
   No stale data issues since we iterate through historical candles.

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis_v5.strategy_v5 import SectorScorer, SectorScore, StockGrader, ExecutionFilters
from analysis_v5 import indicators_v5 as ind
from core_v5 import config_v5 as config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SectorEngineV5")


@dataclass
class BacktestTrade:
    """Represents a single trade in the backtest."""
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
    highest_price: float
    lowest_price: float
    sector: str
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    realized_pnl: float = 0.0


class SectorBacktesterV5:
    """
    V5 Backtest Engine aligned with Production (main_v5.py).
    
    Key Differences from V4:
    1. Previous Close Anchor: All percentage calcs use previous close
    2. No Redundant Refresh: Continuous 5-min candle processing
    3. Fresh RVOL: Calculated from actual 5-min candles at each timestamp
    """
    
    def __init__(self, data_root: Path = None):
        if data_root is None:
            data_root = Path(__file__).parent / "data"
        self.data_root = data_root
        
        # Data Storage
        self.daily_data: Dict[str, pd.DataFrame] = {}
        self.intra_data: Dict[str, pd.DataFrame] = {}
        
        # Strategy Components
        self.scorer = SectorScorer()
        self.grader = StockGrader()
        
        # Portfolio State
        self.equity = 1000000.0  # Rs.10 Lakh
        self.initial_equity = 1000000.0
        self.daily_start_equity = 1000000.0
        self.active_trades: Dict[str, BacktestTrade] = {}
        self.trade_history: List[BacktestTrade] = []
        
        # Universe Metadata
        self.indices: List[Dict] = []
        self.sector_map: Dict[str, List[str]] = {}  # Sector Name -> [Stocks]
        
        # V5: Previous Close Cache (Golden Anchor)
        self.prev_close_cache: Dict[str, float] = {}  # Symbol -> Previous Close
        
        # VIX History for Percentile Calculation
        self.vix_history: List[float] = []
        
        # Rejection Cooldown (Symbol -> Timestamp)
        self.rejected_symbols: Dict[str, datetime] = {}
        
    def initialize(self):
        """Load universe and preload all data into memory."""
        import json
        
        # 1. Load Universe
        if not config.UNIVERSE_PATH.exists():
            logger.error("Universe file missing.")
            return False

        with open(config.UNIVERSE_PATH, 'r') as f:
            data = json.load(f)
            self.indices = data['indices']
            for s in data['stocks']:
                for sec in s.get('indices', []):
                    if sec not in self.sector_map:
                        self.sector_map[sec] = []
                    self.sector_map[sec].append(s['symbol'])

        # 2. Preload Data
        symbols = ["NIFTY 50", "INDIA VIX"] + [i['symbol'] for i in self.indices]
        for sector_stocks in self.sector_map.values():
            symbols.extend(sector_stocks)
        
        symbols = list(set(symbols))
        logger.info(f"Preloading {len(symbols)} instruments into RAM...")
        
        loaded_daily = 0
        loaded_intra = 0
        
        for sym in symbols:
            # Daily Data
            d_path = self.data_root / "daily" / f"{sym}.parquet"
            if d_path.exists():
                df = pd.read_parquet(d_path).sort_values('date')
                self.daily_data[sym] = df
                loaded_daily += 1
                
                # Store VIX history
                if sym == "INDIA VIX":
                    self.vix_history = [d['close'] for d in df.to_dict('records')]
            
            # Intraday (5-minute) Data
            i_path = self.data_root / "5minute" / f"{sym}.parquet"
            if i_path.exists():
                df = pd.read_parquet(i_path).sort_values('date')
                
                # Pre-calculate VWAP
                df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
                df['tp_vol'] = df['typical_price'] * df['volume']
                df['date_only'] = df['date'].dt.date
                df['cum_vol'] = df.groupby('date_only')['volume'].cumsum()
                df['cum_tp_vol'] = df.groupby('date_only')['tp_vol'].cumsum()
                df['vwap'] = df['cum_tp_vol'] / df['cum_vol']
                
                self.intra_data[sym] = df
                loaded_intra += 1
        
        logger.info(f"Loaded {loaded_daily} daily, {loaded_intra} intraday files.")
        return True

    def _validate_data_sufficiency(self, start_date: datetime.date) -> bool:
        """Ensure sufficient history exists for indicator calculations."""
        required_start = start_date - timedelta(days=config.LOOKBACK_DAYS_VIX)
        
        has_nifty = "NIFTY 50" in self.daily_data and not self.daily_data["NIFTY 50"].empty
        has_vix = "INDIA VIX" in self.daily_data and not self.daily_data["INDIA VIX"].empty
        
        if not has_nifty:
            logger.error("NIFTY 50 daily data missing. Run data_miner_v5.py first.")
            return False
        
        if not has_vix:
            logger.error("INDIA VIX daily data missing. Run data_miner_v5.py first.")
            return False

        first_available = self.daily_data["NIFTY 50"].iloc[0]['date'].date()
        if first_available > required_start:
            logger.error(f"Insufficient History. Have {first_available}, need {required_start}.")
            return False
            
        logger.info("Data Sufficiency Check Passed.")
        return True

    def _setup_previous_close_anchors(self, target_date: datetime.date):
        """
        V5 FIX: Pre-calculate Previous Close for all symbols.
        This is the "Golden Anchor" for percentage calculations.
        """
        self.prev_close_cache.clear()
        
        # For each symbol, find the last trading day's close before target_date
        all_symbols = set(["NIFTY 50"])
        for idx in self.indices:
            all_symbols.add(idx['symbol'])
        for stocks in self.sector_map.values():
            all_symbols.update(stocks)
        
        for sym in all_symbols:
            d_df = self.daily_data.get(sym)
            if d_df is None or d_df.empty:
                continue
            
            # Get the last close before target_date
            d_hist = d_df[d_df['date'].dt.date < target_date]
            if not d_hist.empty:
                self.prev_close_cache[sym] = float(d_hist.iloc[-1]['close'])

    def _get_vix_percentile(self, timestamp: datetime) -> float:
        """Calculate VIX percentile based on historical data."""
        if not self.vix_history:
            return 50.0
        
        vix_current = 0.0
        vix_df = self.daily_data.get("INDIA VIX")
        if vix_df is not None:
            mask = vix_df['date'].dt.date <= timestamp.date()
            if mask.any():
                vix_current = vix_df[mask].iloc[-1]['close']
        
        if vix_current <= 0:
            return 50.0
        
        # Use last 20 VIX values for percentile (rolling window)
        vix_window = self.vix_history[-20:] if len(self.vix_history) >= 20 else self.vix_history
        count_below = sum(1 for v in vix_window if v < vix_current)
        return (count_below / len(vix_window)) * 100 if vix_window else 50.0

    def _get_vix_multiplier(self, vix_pctl: float) -> float:
        """Get VIX-based sizing multiplier."""
        if vix_pctl >= config.VIX_PCTL_EXTREME_THRESHOLD:
            return config.VIX_MULT_HIGH
        elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
            return config.VIX_MULT_HIGH
        elif vix_pctl > 50:
            return config.VIX_MULT_ELEVATED
        elif vix_pctl > config.VIX_PCTL_LOW_THRESHOLD:
            return config.VIX_MULT_NORMAL
        else:
            return config.VIX_MULT_LOW

    def _get_day_state_multiplier(self, timestamp: datetime, daily_pnl_pct: float) -> float:
        """Get day state multiplier (Lunch period, Drawdown warning)."""
        mult = 1.0
        
        # Lunch Lull (12:00 - 13:15) -> 70%
        if dt_time(12, 0) <= timestamp.time() < dt_time(13, 15):
            mult = config.RISK_MULT_LUNCH
        
        # Daily DD Warning (-1%) -> 50%
        if daily_pnl_pct <= config.DAILY_DRAWDOWN_WARNING_PCT:
            mult = config.RISK_MULT_WARNING
        
        return mult

    def _get_playbook(self, t: dt_time) -> str:
        """Determine current market phase."""
        if t < config.MARKET_OPEN_TIME:
            return "PRE_MARKET"
        if t < config.OR_START_TIME:
            return "WAIT"
        if t < config.ORB_START_TIME:
            return "OR_FORMATION"
        if t < config.GAP_START_TIME:
            return "ORB"
        if t < config.MAIN_START_TIME:
            return "GAP"
        if t < config.ENTRY_CUTOFF_TIME:
            return "MAIN"
        if t < config.FORCE_EXIT_TIME:
            return "EXIT_ONLY"
        return "FORCE_EXIT"

    def _calculate_chandelier(self, trade: BacktestTrade, timestamp: datetime) -> float:
        """Calculate Chandelier trailing stop."""
        atr_buffer = trade.atr_at_entry * config.CHANDELIER_ATR_MULT
        
        i_df = self.intra_data.get(trade.symbol)
        if i_df is None:
            return trade.current_stop
        
        lookback = i_df[i_df['date'] <= timestamp].tail(config.CHANDELIER_LOOKBACK)
        if len(lookback) < config.CHANDELIER_LOOKBACK:
            return trade.current_stop
        
        if trade.direction == "LONG":
            anchor = max(lookback['high'].max(), trade.highest_price)
            return anchor - atr_buffer
        else:
            anchor = min(lookback['low'].min(), trade.lowest_price)
            return anchor + atr_buffer

    def _update_trades(self, timestamp: datetime):
        """Process active trades: Check SL, T1, and Trailing."""
        closed_symbols = []
        
        for sym, trade in self.active_trades.items():
            i_df = self.intra_data.get(sym)
            if i_df is None:
                continue
            
            # Get current 5-min candle
            row = i_df[i_df['date'] == timestamp]
            if row.empty:
                continue
            curr = row.iloc[0]
            
            # Update High/Low trackers
            trade.highest_price = max(trade.highest_price, curr['high'])
            trade.lowest_price = min(trade.lowest_price, curr['low'])
            
            # 1. Check Stop Loss
            stop_hit = (trade.direction == "LONG" and curr['low'] <= trade.current_stop) or \
                       (trade.direction == "SHORT" and curr['high'] >= trade.current_stop)
            
            if stop_hit:
                exit_p = trade.current_stop
                pnl = (exit_p - trade.entry_price) * trade.qty if trade.direction == "LONG" else (trade.entry_price - exit_p) * trade.qty
                trade.realized_pnl += pnl
                self.equity += pnl
                trade.exit_price = exit_p
                trade.exit_time = timestamp
                trade.stage = "CLOSED"
                self.trade_history.append(trade)
                closed_symbols.append(sym)
                continue

            # 2. Check Target 1 (1.5R)
            if trade.stage == "ACTIVE":
                target_hit = (trade.direction == "LONG" and curr['high'] >= trade.target_1) or \
                             (trade.direction == "SHORT" and curr['low'] <= trade.target_1)
                
                if target_hit:
                    partial_qty = max(1, int(trade.qty * config.TARGET_1_EXIT_PCT))
                    pnl = (trade.target_1 - trade.entry_price) * partial_qty if trade.direction == "LONG" else (trade.entry_price - trade.target_1) * partial_qty
                    trade.realized_pnl += pnl
                    self.equity += pnl
                    trade.qty -= partial_qty
                    trade.current_stop = trade.entry_price  # Move to breakeven
                    trade.stage = "PARTIAL"
                    logger.info(f"   TARGET 1 HIT: {trade.symbol} at {timestamp.strftime('%H:%M')}")

            # 3. Chandelier Trailing (for PARTIAL stage)
            if trade.stage == "PARTIAL":
                new_stop = self._calculate_chandelier(trade, timestamp)
                if trade.direction == "LONG":
                    trade.current_stop = max(trade.current_stop, new_stop)
                else:
                    trade.current_stop = min(trade.current_stop, new_stop)

        # Cleanup closed trades
        for sym in closed_symbols:
            del self.active_trades[sym]

    def _execute_trade(self, symbol: str, direction: str, grade: str, price: float, 
                       atr: float, sector: str, timestamp: datetime):
        """Execute a new trade with risk checks."""
        # Check Rejection Cooldown (5 mins)
        if symbol in self.rejected_symbols:
            if timestamp - self.rejected_symbols[symbol] < timedelta(minutes=5):
                return
            else:
                del self.rejected_symbols[symbol]

        # Risk Limits
        if len(self.active_trades) >= config.MAX_CONCURRENT_POSITIONS:
            return
        
        sector_count = sum(1 for t in self.active_trades.values() if t.sector == sector)
        if sector_count >= config.MAX_POSITIONS_PER_SECTOR:
            return
        
        if symbol in self.active_trades:
            return

        # Sizing
        current_playbook = self._get_playbook(timestamp.time())
        stop_mult = config.STOP_ATR_MULT_ORB if current_playbook == "ORB" else config.STOP_ATR_MULT_MAIN
        
        stop_dist = atr * stop_mult
        stop_p = price - stop_dist if direction == "LONG" else price + stop_dist
        
        # VIX and Day State Multipliers
        vix_pctl = self._get_vix_percentile(timestamp)
        vix_mult = self._get_vix_multiplier(vix_pctl)
        
        daily_pnl_pct = ((self.equity - self.daily_start_equity) / self.daily_start_equity * 100) if self.daily_start_equity > 0 else 0.0
        day_state_mult = self._get_day_state_multiplier(timestamp, daily_pnl_pct)
        
        base_risk = self.equity * config.BASE_RISK_PER_TRADE_PCT
        grade_mult = config.GRADE_MULTIPLIERS.get(grade, 0.0)
        
        total_mult = grade_mult * vix_mult * day_state_mult
        risk_amount = base_risk * total_mult
        qty = int(risk_amount / stop_dist)
        
        if qty < 1:
            self.rejected_symbols[symbol] = timestamp
            return
        
        # Target 1 (1.5R)
        risk_val = abs(price - stop_p)
        t1_dist = risk_val * config.TARGET_1_MULT
        t1 = price + t1_dist if direction == "LONG" else price - t1_dist
        
        # Create Trade
        self.active_trades[symbol] = BacktestTrade(
            symbol=symbol, direction=direction, entry_price=price, qty=qty,
            initial_stop=stop_p, current_stop=stop_p, target_1=t1,
            stage="ACTIVE", entry_time=timestamp, atr_at_entry=atr,
            highest_price=price, lowest_price=price, sector=sector
        )

    def _get_hma_alignment(self, sym: str, current_price: float, timestamp: datetime, target_date: datetime.date) -> str:
        """
        Calculate HMA alignment (matching main_v5.py logic).
        Uses daily HMA9 and 5m HMA20.
        """
        d_df = self.daily_data.get(sym)
        i_df = self.intra_data.get(sym)
        
        if d_df is None or i_df is None:
            return "MIXED"
        
        d_hist = d_df[d_df['date'].dt.date < target_date]
        i_hist = i_df[i_df['date'] <= timestamp]
        
        if len(d_hist) < 20 or len(i_hist) < 21:
            return "MIXED"
        
        # Prepare Price Series
        closes_d = np.append(d_hist['close'].values, current_price)
        closes_5m = i_hist['close'].values
        
        # Tactical Trend: HMA 9 (Daily)
        hma9_curr = ind.calculate_hma(closes_d, 9)
        hma9_prev = ind.calculate_hma(closes_d[:-1], 9)
        
        # Intraday Trend: HMA 20 (5m)
        hma20_curr = ind.calculate_hma(closes_5m, 20)
        hma20_prev = ind.calculate_hma(closes_5m[:-1], 20)
        
        # Determine Alignment (Position AND Slope)
        h9_bull = (current_price > hma9_curr and ind.calculate_slope(hma9_curr, hma9_prev) == "UP")
        h20_bull = (current_price > hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "UP")
        
        h9_bear = (current_price < hma9_curr and ind.calculate_slope(hma9_curr, hma9_prev) == "DOWN")
        h20_bear = (current_price < hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "DOWN")
        
        if h9_bull and h20_bull:
            return "BULLISH"
        if h9_bear and h20_bear:
            return "BEARISH"
        return "MIXED"

    def _scan_stocks(self, selected_sectors: List[str], final_scores: List[SectorScore], 
                     timestamp: datetime, target_date: datetime.date) -> List[Dict]:
        """Grade stocks within selected sectors and execute trades."""
        
        current_playbook = self._get_playbook(timestamp.time())
        
        # Only allow entries during ORB or MAIN
        if current_playbook not in ["ORB", "MAIN"]:
            return []

        signals = []
        sec_info_map = {s.symbol: s for s in final_scores}
        
        # Collect target stocks
        target_stocks = []
        for sec_sym in selected_sectors:
            sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
            if sec_name:
                target_stocks.extend([(s, sec_sym) for s in self.sector_map.get(sec_name, [])])
        
        # Force-add active positions to scan list
        for active_sym in self.active_trades.keys():
            if active_sym not in [s[0] for s in target_stocks]:
                active_sector = next((i['symbol'] for i in self.indices 
                                     if i['name'] == self.active_trades[active_sym].sector), None)
                if active_sector:
                    target_stocks.append((active_sym, active_sector))
        
        for sym, sec_sym in target_stocks:
            d_df = self.daily_data.get(sym)
            i_df = self.intra_data.get(sym)
            if d_df is None or i_df is None:
                continue
            
            d_hist = d_df[d_df['date'].dt.date < target_date]
            i_hist = i_df[i_df['date'] <= timestamp]
            if len(d_hist) < 40 or len(i_hist) < 20:
                continue
            
            curr_price = i_hist.iloc[-1]['close']
            
            # ADV Filter
            d_closes = d_hist['close'].values
            adv = ExecutionFilters.calculate_adv_crores(d_closes, d_hist['volume'].values)
            if adv < config.MIN_ADV_CRORES:
                continue
            
            # HMA Alignment (V5: matching main_v5.py)
            hma_align = self._get_hma_alignment(sym, curr_price, timestamp, target_date)
            
            # StochRSI
            sim_d_closes = np.append(d_closes, curr_price)
            stoch_k, _ = ind.calculate_stoch_rsi(sim_d_closes)
            
            # V5 FIX: RVOL uses actual 5m candles (fresh data at each timestamp)
            recent_vols = i_hist['volume'].values[-20:]
            if len(recent_vols) >= 2:
                rvol = ind.calculate_rvol(recent_vols[-1], np.mean(recent_vols[:-1]))
            else:
                rvol = 1.0
            
            # Grading
            sec_info = sec_info_map.get(sec_sym)
            vix_pctl = self._get_vix_percentile(timestamp)
            spread_atr = 0.1  # Neutral value for backtest (no order book)
            
            signal = self.grader.calculate_grade(
                hma_align, rvol, stoch_k, 
                sec_info.rank if sec_info else 10, 
                spread_atr, current_playbook, vix_pctl
            )
            
            # Directional Filter
            sec_bias = sec_info.bias if sec_info else "NEUTRAL"
            if (sec_bias == "LONG" and signal.direction == "LONG") or \
               (sec_bias == "SHORT" and signal.direction == "SHORT"):
                if signal.grade in ["A+", "A"]:
                    signals.append({
                        'sym': sym, 
                        'grade': signal.grade, 
                        'score': signal.score, 
                        'direction': signal.direction
                    })
                    
                    # ATR for stop calculation
                    atr = ind.calculate_atr(
                        d_hist['high'].values, 
                        d_hist['low'].values, 
                        d_hist['close'].values, 10
                    )
                    
                    sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
                    self._execute_trade(sym, signal.direction, signal.grade, curr_price, atr, sec_name, timestamp)
        
        return sorted(signals, key=lambda x: x['score'], reverse=True)[:5]

    def _run_day(self, target_date: datetime.date):
        """Simulate a single trading day in 5-minute steps."""
        if "NIFTY 50" not in self.intra_data:
            return
        
        nifty_day = self.intra_data["NIFTY 50"][
            self.intra_data["NIFTY 50"]['date'].dt.date == target_date
        ]
        if nifty_day.empty:
            return

        # V5: Setup Previous Close anchors for this day
        self._setup_previous_close_anchors(target_date)
        
        # Get historical references for RS calculation
        n_hist = self.daily_data.get("NIFTY 50")
        if n_hist is None:
            return
        n_prev = n_hist[n_hist['date'].dt.date < target_date].tail(20)
        if len(n_prev) < 20:
            return
        
        n_20 = n_prev.iloc[0]['close']
        n_3 = n_prev.iloc[-3]['close']
        
        for _, row in nifty_day.iterrows():
            ts = row['date']
            
            # A. Update Active Trades (Exits/Trailing)
            self._update_trades(ts)
            
            # B. Force Exit at 15:05
            if ts.time() >= dt_time(15, 5) and self.active_trades:
                for sym in list(self.active_trades.keys()):
                    trade = self.active_trades[sym]
                    i_df = self.intra_data.get(sym)
                    curr_p = i_df[i_df['date'] <= ts].iloc[-1]['close'] if i_df is not None else trade.entry_price
                    pnl = (curr_p - trade.entry_price) * trade.qty if trade.direction == "LONG" else (trade.entry_price - curr_p) * trade.qty
                    self.equity += pnl
                    trade.realized_pnl += pnl
                    trade.exit_price = curr_p
                    trade.exit_time = ts
                    trade.stage = "CLOSED"
                    self.trade_history.append(trade)
                    del self.active_trades[sym]

            # C. Nifty Metrics (V5: using Previous Close)
            nifty_prev_close = self.prev_close_cache.get("NIFTY 50", row['open'])
            nifty_curr = row['close']
            nifty_pct = ((nifty_curr - nifty_prev_close) / nifty_prev_close) * 100 if nifty_prev_close > 0 else 0.0
            
            # D. Regime Detection
            vix_pctl = self._get_vix_percentile(ts)
            if vix_pctl >= config.VIX_PCTL_EXTREME_THRESHOLD:
                regime = "EXTREME"
            elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
                regime = "MEAN_REVERT"
            elif vix_pctl <= config.VIX_PCTL_LOW_THRESHOLD:
                regime = "TRENDING"
            else:
                regime = "NEUTRAL"

            # E. Sector Scoring (V5: uses Previous Close)
            scores = []
            for idx in self.indices:
                sym = idx['symbol']
                name = idx['name']
                
                if name in ["NIFTY 50", "INDIA VIX"]:
                    continue
                
                d_hist = self.daily_data.get(sym)
                if d_hist is None:
                    continue
                
                d_prev = d_hist[d_hist['date'].dt.date < target_date].tail(20)
                if len(d_prev) < 20:
                    continue
                
                i_df = self.intra_data.get(sym)
                if i_df is None:
                    continue
                i_row = i_df[i_df['date'] == ts]
                if i_row.empty:
                    continue
                
                sec_curr = i_row.iloc[0]['close']
                
                # V5 FIX: Use Previous Close as anchor
                sec_prev_close = self.prev_close_cache.get(sym, 0)
                if sec_prev_close == 0:
                    continue
                
                s_20 = d_prev.iloc[0]['close']
                s_3 = d_prev.iloc[-3]['close']
                
                # RS Calculations (Subtraction Method)
                struct_rs = ((sec_curr - s_20) / s_20 - (nifty_curr - n_20) / n_20) * 100
                short_rs = ((sec_curr - s_3) / s_3 - (nifty_curr - n_3) / n_3) * 100
                
                # V5 FIX: Daily RS uses Previous Close as anchor
                sec_daily_ret = (sec_curr - sec_prev_close) / sec_prev_close if sec_prev_close > 0 else 0
                nifty_daily_ret = (nifty_curr - nifty_prev_close) / nifty_prev_close if nifty_prev_close > 0 else 0
                daily_rs = (sec_daily_ret - nifty_daily_ret) * 100
                
                # Breadth Calculation
                constituents = self.sector_map.get(name, [])
                above = 0
                below = 0
                valid = 0
                
                for s_sym in constituents:
                    s_df = self.intra_data.get(s_sym)
                    if s_df is None:
                        continue
                    s_row = s_df[s_df['date'] == ts]
                    if s_row.empty:
                        continue
                    valid += 1
                    if s_row.iloc[0]['close'] > s_row.iloc[0]['vwap']:
                        above += 1
                    elif s_row.iloc[0]['close'] < s_row.iloc[0]['vwap']:
                        below += 1
                
                net_breadth = (above / valid - below / valid) if valid > 0 else 0.0
                
                scores.append(SectorScore(
                    symbol=sym,
                    price=sec_curr,
                    change_pct=sec_daily_ret * 100,  # V5: Daily change from Previous Close
                    structural_rs=struct_rs,
                    shortterm_rs=short_rs,
                    intraday_rs=daily_rs,  # V5: Daily RS
                    breadth=net_breadth
                ))
            
            # F. Rank and Select
            final_scores = self.scorer.score_all(scores, regime, nifty_pct)
            selected = self.scorer.select_top_n(final_scores)
            
            # G. Scan & Trade
            self._scan_stocks(selected, final_scores, ts, target_date)

    def run_backtest(self, start_date: datetime.date, end_date: datetime.date):
        """Run the backtest simulation over a date range."""
        if not self._validate_data_sufficiency(start_date):
            return

        # Identify trading days
        trading_days = []
        current_date = start_date
        
        logger.info(f"Scanning for trading days between {start_date} and {end_date}...")
        while current_date <= end_date:
            if "NIFTY 50" in self.intra_data:
                day_data = self.intra_data["NIFTY 50"]
                if not day_data[day_data['date'].dt.date == current_date].empty:
                    trading_days.append(current_date)
            current_date += timedelta(days=1)
        
        logger.info(f"Found {len(trading_days)} trading sessions.")
        
        # Print Header
        print("\n" + "=" * 140)
        print(f"{'DATE':<12} | {'START EQUITY':<15} | {'END EQUITY':<15} | {'DAY PnL':<12} | {'TRADES':<6} | {'TRADE PNLS'}")
        print("=" * 140)
        
        for day in trading_days:
            start_eq = self.equity
            self.daily_start_equity = start_eq
            
            # Run simulation
            self._run_day(day)
            
            day_pnl = self.equity - start_eq
            
            # Get trades for this day
            day_trades = [t for t in self.trade_history if t.entry_time.date() == day]
            trade_pnls_str = ", ".join([f"{t.realized_pnl:,.0f}" for t in day_trades])
            
            print(f"{day}   | Rs.{start_eq:<14,.0f} | Rs.{self.equity:<14,.0f} | Rs.{day_pnl:>10,.0f} | {len(day_trades):<6} | {trade_pnls_str}")
            
            # Reset daily state
            self.active_trades.clear()
            self.rejected_symbols.clear()

        # Final Summary
        self._print_grand_summary(len(trading_days))

    def _print_grand_summary(self, total_days: int):
        """Print comprehensive backtest summary."""
        print("\n" + "=" * 70)
        print(f"V5 BACKTEST SUMMARY (Previous Close Anchor)")
        print("-" * 70)
        print(f"Days Traded:        {total_days}")
        print(f"Initial Equity:     Rs.{self.initial_equity:,.0f}")
        print(f"Final Equity:       Rs.{self.equity:,.0f}")
        
        abs_return = self.equity - self.initial_equity
        pct_return = ((self.equity / self.initial_equity) - 1) * 100
        print(f"Total Return:       Rs.{abs_return:,.0f} ({pct_return:.2f}%)")
        
        print(f"\nTotal Trades:       {len(self.trade_history)}")
        
        if self.trade_history:
            wins = sum(1 for t in self.trade_history if t.realized_pnl > 0)
            losses = sum(1 for t in self.trade_history if t.realized_pnl < 0)
            
            print(f"Win Rate:           {wins/len(self.trade_history):.1%}")
            print(f"Wins/Losses:        {wins}/{losses}")
            
            pnls = [t.realized_pnl for t in self.trade_history]
            avg_pnl = sum(pnls) / len(pnls)
            std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
            sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0
            
            print(f"Expectancy:         Rs.{avg_pnl:,.0f} per trade")
            print(f"Sharpe Ratio:       {sharpe:.2f}")
            
            max_win = max(pnls)
            max_loss = min(pnls)
            
            winning_trades = [p for p in pnls if p > 0]
            losing_trades = [p for p in pnls if p < 0]
            profit_factor = sum(winning_trades) / abs(sum(losing_trades)) if losing_trades else float('inf')
            
            print(f"Max Win:            Rs.{max_win:,.0f}")
            print(f"Max Loss:           Rs.{max_loss:,.0f}")
            print(f"Profit Factor:      {profit_factor:.2f}")
            
            # Calculate max drawdown
            equity_curve = [self.initial_equity]
            for t in sorted(self.trade_history, key=lambda x: x.exit_time or x.entry_time):
                equity_curve.append(equity_curve[-1] + t.realized_pnl)
            
            peak = equity_curve[0]
            max_dd = 0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            
            print(f"Max Drawdown:       {max_dd:.2f}%")
        
        print("=" * 70 + "\n")

    def export_trades(self, filepath: str = None):
        """Export trade history to CSV."""
        if filepath is None:
            filepath = self.data_root / "backtest_trades_v5.csv"
        
        if not self.trade_history:
            logger.warning("No trades to export.")
            return
        
        trades_data = []
        for t in self.trade_history:
            trades_data.append({
                'symbol': t.symbol,
                'direction': t.direction,
                'entry_time': t.entry_time,
                'entry_price': t.entry_price,
                'exit_time': t.exit_time,
                'exit_price': t.exit_price,
                'qty': t.qty,
                'pnl': t.realized_pnl,
                'sector': t.sector,
                'stage': t.stage
            })
        
        df = pd.DataFrame(trades_data)
        df.to_csv(filepath, index=False)
        logger.info(f"Exported {len(trades_data)} trades to {filepath}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V5 Sector Backtest Engine")
    parser.add_argument("--start", type=str, default="2026-01-05", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-01-10", help="End date (YYYY-MM-DD)")
    parser.add_argument("--export", action="store_true", help="Export trades to CSV")
    
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    engine = SectorBacktesterV5()
    
    if engine.initialize():
        engine.run_backtest(start_date, end_date)
        
        if args.export:
            engine.export_trades()
