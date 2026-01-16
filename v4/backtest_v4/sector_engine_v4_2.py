"""
================================================================================
V4 SECTOR BACKTEST ENGINE (V4.2 - HIGH FIDELITY)
================================================================================
Validates Sector Ranking logic with exact Production Timing & Playbook phases.

Changes in v4.2:
- Implemented strict Playbook phases (ORB vs MAIN).
- Enforces NO TRADE zones (Wait: 9:15-9:35, Gap: 10:05-10:10).
- Dynamically passes Playbook to StockGrader for variable RVOL/Spread thresholds.

Features:
- Daily & 5-Min Data Alignment.
- Real-time Breadth simulation.
- Lifecycle Management (Target 1.5R, Chandelier Trail).

Author: Sector Analysis System
Version: 4.2.0
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

# Add parent directory to path to import production modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis_v4.strategy_v4 import SectorScorer, SectorScore, StockGrader, ExecutionFilters, StockSignal
from analysis_v4 import indicators_v4 as ind
from core_v4 import config_v4 as config

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SectorEngine")

@dataclass
class BacktestTrade:
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

class SectorBacktester:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.daily_data: Dict[str, pd.DataFrame] = {}
        self.intra_data: Dict[str, pd.DataFrame] = {}
        self.scorer = SectorScorer()
        self.grader = StockGrader()
        
        # Portfolio State
        self.equity = 1000000.0  # ₹10 Lakh
        self.initial_equity = 1000000.0
        self.active_trades: Dict[str, BacktestTrade] = {}
        self.trade_history: List[BacktestTrade] = []
        
        # Universe Metadata
        self.indices = []
        self.sector_map = {} # Sector Name -> [Stocks]
        
    def initialize(self):
        """Load universe and preload all indices and stocks into memory."""
        # 1. Load Universe
        import json
        if not config.UNIVERSE_PATH.exists():
            logger.error("Universe file missing.")
            return

        with open(config.UNIVERSE_PATH, 'r') as f:
            data = json.load(f)
            self.indices = data['indices']
            for s in data['stocks']:
                for sec in s.get('indices', []):
                    if sec not in self.sector_map: self.sector_map[sec] = []
                    self.sector_map[sec].append(s['symbol'])

        # 2. Preload Data
        symbols = ["NIFTY 50"] + [i['symbol'] for i in self.indices]
        for sector_stocks in self.sector_map.values():
            symbols.extend(sector_stocks)
        
        symbols = list(set(symbols)) # Unique
        logger.info(f"💾 Preloading {len(symbols)} instruments into RAM...")
        
        for sym in symbols:
            # Daily
            d_path = self.data_root / "daily" / f"{sym}.parquet"
            if d_path.exists():
                self.daily_data[sym] = pd.read_parquet(d_path).sort_values('date')
            
            # Intra
            i_path = self.data_root / "5minute" / f"{sym}.parquet"
            if i_path.exists():
                df = pd.read_parquet(i_path).sort_values('date')
                # Pre-calculate VWAP for the day
                df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
                df['tp_vol'] = df['typical_price'] * df['volume']
                # Cumulative per day
                df['date_only'] = df['date'].dt.date
                df['cum_vol'] = df.groupby('date_only')['volume'].cumsum()
                df['cum_tp_vol'] = df.groupby('date_only')['tp_vol'].cumsum()
                df['vwap'] = df['cum_tp_vol'] / df['cum_vol']
                self.intra_data[sym] = df

    def _validate_data_sufficiency(self, start_date: datetime.date) -> bool:
        """Ensure we have at least 30 days of history before the start date for indicators."""
        required_start = start_date - timedelta(days=config.LOOKBACK_DAYS_VIX) # Using VIX lookback as proxy for sufficient history
        
        has_nifty = "NIFTY 50" in self.daily_data and not self.daily_data["NIFTY 50"].empty
        
        if not has_nifty:
            logger.error("❌ NIFTY 50 daily data missing. Please run data_miner.py first.")
            return False

        first_available = self.daily_data["NIFTY 50"].iloc[0]['date'].date()
        if first_available > required_start:
            logger.error(f"❌ Insufficient History. Have data from {first_available}, need {required_start}. Please run data_miner.py.")
            return False
            
        logger.info("✅ Data Sufficiency Check Passed.")
        return True

    def _get_playbook(self, t: dt_time) -> str:
        """Determine current market phase based on config timings."""
        if t < config.MARKET_OPEN_TIME: return "PRE_MARKET"
        if t < config.OR_START_TIME: return "WAIT"
        if t < config.ORB_START_TIME: return "OR_FORMATION"
        if t < config.GAP_START_TIME: return "ORB"
        if t < config.MAIN_START_TIME: return "GAP"
        if t < config.ENTRY_CUTOFF_TIME: return "MAIN"
        if t < config.FORCE_EXIT_TIME: return "EXIT_ONLY"
        return "FORCE_EXIT"

    def _calculate_chandelier(self, trade: BacktestTrade, timestamp: datetime) -> float:
        """Cloned Chandelier logic from lifecycle_v4.py."""
        atr_buffer = trade.atr_at_entry * config.CHANDELIER_ATR_MULT
        
        # Get last 10 5-min bars for extreme
        i_df = self.intra_data.get(trade.symbol)
        if i_df is None: return trade.current_stop
        
        # Lookback 10 bars
        lookback = i_df[i_df['date'] <= timestamp].tail(config.CHANDELIER_LOOKBACK)
        if len(lookback) < config.CHANDELIER_LOOKBACK: return trade.current_stop
        
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
            if i_df is None: continue
            
            # Get current 5-min candle
            row = i_df[i_df['date'] == timestamp]
            if row.empty: continue
            curr = row.iloc[0]
            
            # Update High/Low trackers
            trade.highest_price = max(trade.highest_price, curr['high'])
            trade.lowest_price = min(trade.lowest_price, curr['low'])
            
            # 1. Check Stop Loss
            stop_hit = (trade.direction == "LONG" and curr['low'] <= trade.current_stop) or \
                       (trade.direction == "SHORT" and curr['high'] >= trade.current_stop)
            
            if stop_hit:
                # Close Full Position at stop price (or current open if gap)
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
                    # Sell 50% at Target Price
                    partial_qty = max(1, int(trade.qty * config.TARGET_1_EXIT_PCT))
                    pnl = (trade.target_1 - trade.entry_price) * partial_qty if trade.direction == "LONG" else (trade.entry_price - trade.target_1) * partial_qty
                    trade.realized_pnl += pnl
                    self.equity += pnl
                    trade.qty -= partial_qty
                    # Move stop to breakeven
                    trade.current_stop = trade.entry_price
                    trade.stage = "PARTIAL"
                    logger.info(f"🎯 TARGET 1 HIT: {trade.symbol} at {timestamp.strftime('%H:%M')}")

            # 3. Check Chandelier Trailing
            if trade.stage == "PARTIAL":
                new_stop = self._calculate_chandelier(trade, timestamp)
                if trade.direction == "LONG":
                    trade.current_stop = max(trade.current_stop, new_stop)
                else:
                    trade.current_stop = min(trade.current_stop, new_stop)

        # Cleanup
        for sym in closed_symbols:
            del self.active_trades[sym]

    def _execute_trade(self, symbol: str, direction: str, grade: str, price: float, atr: float, sector: str, timestamp: datetime):
        """Check risk and enter new trade."""
        # 1. Risk Limits
        if len(self.active_trades) >= config.MAX_CONCURRENT_POSITIONS: return
        
        sector_count = sum(1 for t in self.active_trades.values() if t.sector == sector)
        if sector_count >= config.MAX_POSITIONS_PER_SECTOR: return
        
        if symbol in self.active_trades: return

        # 2. Sizing
        base_risk = self.equity * config.BASE_RISK_PER_TRADE_PCT
        grade_mult = config.GRADE_MULTIPLIERS.get(grade, 0.0)
        
        # Calculate stop distance based on Playbook Phase
        current_playbook = self._get_playbook(timestamp.time())
        stop_mult = config.STOP_ATR_MULT_ORB if current_playbook == "ORB" else config.STOP_ATR_MULT_MAIN
        
        stop_dist = atr * stop_mult
        stop_p = price - stop_dist if direction == "LONG" else price + stop_dist
        
        qty = int((base_risk * grade_mult) / stop_dist)
        if qty < 1: return
        
        # 3. Target 1
        risk_val = abs(price - stop_p)
        t1_dist = risk_val * config.TARGET_1_MULT
        t1 = price + t1_dist if direction == "LONG" else price - t1_dist
        
        # 4. Create Trade
        self.active_trades[symbol] = BacktestTrade(
            symbol=symbol, direction=direction, entry_price=price, qty=qty,
            initial_stop=stop_p, current_stop=stop_p, target_1=t1,
            stage="ACTIVE", entry_time=timestamp, atr_at_entry=atr,
            highest_price=price, lowest_price=price, sector=sector
        )

    def _scan_stocks(self, selected_sectors: List[str], final_scores: List[SectorScore], timestamp: datetime) -> List[Dict]:
        """Scan stocks within selected sectors for Grade A+/A signals."""
        
        # 1. Determine Playbook Phase
        current_playbook = self._get_playbook(timestamp.time())
        
        # 2. STRICT ENTRY GATE: Only allow entries during ORB or MAIN
        if current_playbook not in ["ORB", "MAIN"]:
            return []

        signals = []
        
        # Create a map for fast sector info lookup
        sec_info_map = {s.symbol: s for s in final_scores}
        
        # Identify target stocks
        target_stocks = []
        for sec_sym in selected_sectors:
            sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
            if sec_name:
                target_stocks.extend([(s, sec_sym) for s in self.sector_map.get(sec_name, [])])
                
        for sym, sec_sym in target_stocks:
            d_df = self.daily_data.get(sym)
            i_df = self.intra_data.get(sym)
            if d_df is None or i_df is None: continue
            
            d_hist = d_df[d_df['date'].dt.date < timestamp.date()]
            i_hist = i_df[i_df['date'] <= timestamp]
            if len(d_hist) < 40 or len(i_hist) < 20: continue
            
            curr_price = i_hist.iloc[-1]['close']
            
            # ADV Filter
            d_closes = d_hist['close'].values
            adv = ExecutionFilters.calculate_adv_crores(d_closes, d_hist['volume'].values)
            if adv < config.MIN_ADV_CRORES: continue
            
            # Indicators
            sim_d_closes = np.append(d_closes, curr_price)
            hma9 = ind.calculate_hma(sim_d_closes, 9)
            hma9_p = ind.calculate_hma(sim_d_closes[:-1], 9)
            hma20 = ind.calculate_hma(i_hist['close'].values, 20)
            hma20_p = ind.calculate_hma(i_hist['close'].values[:-1], 20)
            
            hma_align = "MIXED"
            if curr_price > hma9 and ind.calculate_slope(hma9, hma9_p) == "UP" and curr_price > hma20 and ind.calculate_slope(hma20, hma20_p) == "UP":
                hma_align = "BULLISH"
            elif curr_price < hma9 and ind.calculate_slope(hma9, hma9_p) == "DOWN" and curr_price < hma20 and ind.calculate_slope(hma20, hma20_p) == "DOWN":
                hma_align = "BEARISH"
            
            stoch_k, _ = ind.calculate_stoch_rsi(sim_d_closes)
            recent_vols = i_hist['volume'].values[-20:]
            rvol = ind.calculate_rvol(recent_vols[-1], np.mean(recent_vols))
            
            # Grading
            sec_info = sec_info_map.get(sec_sym)
            
            # NOTE: We assume VIX Percentile = 50 (Neutral) for backtest as we don't have historical VIX synced perfectly yet.
            # Passing current_playbook allows the Grader to use stricter RVOL/Spread logic for ORB.
            signal = self.grader.calculate_grade(hma_align, rvol, stoch_k, sec_info.rank if sec_info else 10, 0.0, current_playbook, 50)
            
            # Directional Filter
            sec_bias = sec_info.bias if sec_info else "NEUTRAL"
            if (sec_bias == "LONG" and signal.direction == "LONG") or (sec_bias == "SHORT" and signal.direction == "SHORT"):
                if signal.grade in ["A+", "A"]:
                    signals.append({'sym': sym, 'grade': signal.grade, 'score': signal.score, 'direction': signal.direction})
                    # ATR for stop calc
                    atr = ind.calculate_atr(d_hist['high'].values, d_hist['low'].values, d_hist['close'].values, 10)
                    # Attempt Execution
                    self._execute_trade(sym, signal.direction, signal.grade, curr_price, atr, sec_name, timestamp)
                
        return sorted(signals, key=lambda x: x['score'], reverse=True)[:5]

    def run_backtest(self, start_date: datetime.date, end_date: datetime.date):
        """Run simulation sequentially over a date range."""
        if not self._validate_data_sufficiency(start_date):
            return

        current_date = start_date
        trading_days = []
        
        # 1. Identify Valid Trading Days
        logger.info(f"📅 Scanning for trading days between {start_date} and {end_date}...")
        while current_date <= end_date:
            # Check if Nifty has 5-min data for this day
            if "NIFTY 50" in self.intra_data:
                day_data = self.intra_data["NIFTY 50"]
                if not day_data[day_data['date'].dt.date == current_date].empty:
                    trading_days.append(current_date)
            current_date += timedelta(days=1)
            
        logger.info(f"✅ Found {len(trading_days)} trading sessions.")
        
        # 2. Header
        print("\n" + "="*120)
        print(f"{ 'DATE':<12} | {'START EQUITY':<15} | {'END EQUITY':<15} | {'PNL':<15} | {'TRADES':<6} | {'TRADE PNLS'}")
        print("="*120)
        
        for day in trading_days:
            start_eq = self.equity
            self._run_day(day)
            day_pnl = self.equity - start_eq
            
            # Get PnLs of trades closed on this day
            day_trades = [t for t in self.trade_history if t.entry_time.date() == day]
            trade_pnls_str = ", ".join([f"{t.realized_pnl:,.0f}" for t in day_trades])
            
            print(f"{day}   | ₹{start_eq:<14,.0f} | ₹{self.equity:<14,.0f} | ₹{day_pnl:<14,.0f} | {len(day_trades):<6} | {trade_pnls_str}")
            
            # Reset Intraday State (but keep Equity and History)
            self.active_trades.clear()

        # 3. Final Report
        self._print_grand_summary(len(trading_days))

    def _run_day(self, target_date: datetime.date):
        """Simulate a single trading day in 5-minute steps."""
        if "NIFTY 50" not in self.intra_data: return
        nifty_day = self.intra_data["NIFTY 50"][self.intra_data["NIFTY 50"]['date'].dt.date == target_date]
        if nifty_day.empty: return

        # 3. Step Loop
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

            # C. Calculate Unrealized PnL (Skipped for speed in multi-day, only needed for daily PnL check if implemented)
            
            # D. Nifty State
            nifty_open = nifty_day.iloc[0]['open']
            nifty_curr = row['close']
            nifty_pct = ((nifty_curr - nifty_open) / nifty_open) * 100
            
            # E. Sector Processing
            scores = []
            for idx in self.indices:
                sym = idx['symbol']
                name = idx['name']
                if name in ["NIFTY 50", "INDIA VIX"]: continue
                
                d_hist = self.daily_data.get(sym)
                n_hist = self.daily_data.get("NIFTY 50")
                if d_hist is None or n_hist is None: continue
                
                d_prev = d_hist[d_hist['date'].dt.date < target_date].tail(20)
                n_prev = n_hist[n_hist['date'].dt.date < target_date].tail(20)
                if len(d_prev) < 20: continue
                
                i_df = self.intra_data.get(sym)
                if i_df is None: continue
                i_row = i_df[i_df['date'] == ts]
                if i_row.empty: continue
                
                sec_curr = i_row.iloc[0]['close']
                sec_open = i_df[i_df['date'].dt.date == target_date].iloc[0]['open']
                
                n_20 = n_prev.iloc[0]['close']; n_3 = n_prev.iloc[-3]['close']
                s_20 = d_prev.iloc[0]['close']; s_3 = d_prev.iloc[-3]['close']
                
                struct_rs = ((sec_curr - s_20)/s_20 - (nifty_curr - n_20)/n_20) * 100
                short_rs = ((sec_curr - s_3)/s_3 - (nifty_curr - n_3)/n_3) * 100
                intra_rs = ((sec_curr - sec_open)/sec_open - (nifty_curr - nifty_open)/nifty_open) * 100
                
                constituents = self.sector_map.get(name, [])
                above = 0; below = 0; valid = 0
                for s_sym in constituents:
                    s_df = self.intra_data.get(s_sym)
                    if s_df is None: continue
                    s_row = s_df[s_df['date'] == ts]
                    if s_row.empty: continue
                    valid += 1
                    if s_row.iloc[0]['close'] > s_row.iloc[0]['vwap']: above += 1
                    elif s_row.iloc[0]['close'] < s_row.iloc[0]['vwap']: below += 1
                
                net_breadth = (above/valid - below/valid) if valid > 0 else 0.0
                scores.append(SectorScore(symbol=sym, structural_rs=struct_rs, shortterm_rs=short_rs, intraday_rs=intra_rs, breadth=net_breadth))

            # D. Scoring & Ranking
            final_scores = self.scorer.score_all(scores, "NEUTRAL", nifty_pct)
            selected = self.scorer.select_top_n(final_scores)
            
            # E. Scan & Trade
            signals = self._scan_stocks(selected, final_scores, ts)
            
    def _print_grand_summary(self, total_days):
        print("\n" + "="*60)
        print(f"🏁 GRAND BACKTEST SUMMARY")
        print("-" * 60)
        print(f"Days Traded:    {total_days}")
        print(f"Initial Equity: ₹{self.initial_equity:,.0f}")
        print(f"Final Equity:   ₹{self.equity:,.0f}")
        abs_return = self.equity - self.initial_equity
        pct_return = ((self.equity/self.initial_equity)-1) * 100
        print(f"Total Return:   ₹{abs_return:,.0f} ({pct_return:.2f}%)")
        
        print(f"Total Trades:   {len(self.trade_history)}")
        if self.trade_history:
            wins = sum(1 for t in self.trade_history if t.realized_pnl > 0)
            print(f"Win Rate:       {wins/len(self.trade_history):.1%}")
            
            gross_pnl = sum(t.realized_pnl for t in self.trade_history)
            # Simple Sharpe Proxy (Avg Trade / StdDev of Trade PnL)
            pnls = [t.realized_pnl for t in self.trade_history]
            avg_pnl = np.mean(pnls)
            std_pnl = np.std(pnls)
            sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0
            print(f"Expectancy:     ₹{avg_pnl:,.0f} per trade")
            print(f"Sharpe Ratio:   {sharpe:.2f}")
            
        print("="*60 + "\n")

if __name__ == "__main__":
    engine = SectorBacktester(Path(__file__).parent / "data")
    engine.initialize()
    # Run Multi-Day Simulation
    engine.run_backtest(datetime(2026, 1, 5).date(), datetime(2026, 1, 9).date())
