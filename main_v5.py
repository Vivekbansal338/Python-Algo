"""
================================================================================
V5 ORCHESTRATOR (MAIN) - REFINED
================================================================================
The Master Controller. Integrates:
Data -> Strategy -> Signal -> Risk -> Order -> Lifecycle -> UI -> Persistence

V5 FIXES IMPLEMENTED:
1. Percentage Calculation: Uses Previous Close (ohlc.close) as anchor instead of
   Today's Open. This aligns with broker terminals and captures gap moves.
2. Removed Redundant 15-min Logic: System is now purely WebSocket-driven.
   Sector ranks update in real-time via live ticks every UI_REFRESH_INTERVAL.
3. RVOL Stale Data Fix: Implemented periodic re-fetching of 5-minute historical
   data every INTRADAY_REFRESH_INTERVAL_SEC (5 minutes) to keep RVOL and HMA
   indicators fresh throughout the trading session.

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import time
import logging
import signal
import sys
import json
import traceback
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from typing import List, Dict, Any, Tuple
from rich.live import Live

from core_v5 import config_v5 as config
from core_v5.data_v5 import data_manager
from analysis_v5.strategy_v5 import (
    MarketRegimeDetector, SectorScorer, SectorScore, 
    StockGrader, StockSignal, ExecutionFilters
)
from analysis_v5 import indicators_v5 as ind
from execution_v5.risk_v5 import RiskManager
from execution_v5.orders_v5 import OrderManager
from execution_v5.lifecycle_v5 import LifecycleManager
from system_v5.state_v5 import StateManager
from system_v5.ui_v5 import DashboardUI
from system_v5.safety_v5 import SafetyMonitor

# Logging to file ONLY
root_logger = logging.getLogger()
if root_logger.handlers:
    root_logger.handlers = []

logging.basicConfig(
    filename=config.LOG_FILE, 
    level=logging.INFO, 
    format="%(asctime)s %(message)s",
    force=True
)
logger = logging.getLogger("Orchestrator")


class TradingBotV5:
    def __init__(self):
        self.running = True
        
        # Core Modules
        self.state_mgr = StateManager()
        self.risk = RiskManager()
        self.orders = OrderManager()
        self.lifecycle = LifecycleManager(self.orders)
        self.ui = DashboardUI()
        self.safety = SafetyMonitor()
        
        # Strategy Components
        self.regime_detector = MarketRegimeDetector()
        self.sector_scorer = SectorScorer()
        self.stock_grader = StockGrader()
        
        # Universe Data
        self.indices: List[Dict] = []
        self.stocks: List[Dict] = []
        self.sector_map: Dict[str, List[str]] = {}  # Sector -> [Symbols]
        
        # Runtime Metrics
        self.logs = []
        self.current_playbook = "INIT"
        self.vix_percentile = 50.0
        self.vix_multiplier = 1.0
        self.vix_history: List[float] = []
        self.last_ui_update = 0
        
        # V5 NEW: Track last intraday history refresh time (for RVOL/HMA fix)
        self.last_intraday_refresh = 0
        
        # Historical Data Cache
        self.sector_history: Dict[str, List[float]] = {}  # Symbol -> [Closes]
        self.nifty_history: List[float] = []  # Nifty Closes
        
        # V5 FIX: Baselines now stores Previous Close (ohlc.close) as anchor
        # Structure: Sym -> {prev_close, close_3d, close_20d}
        self.baselines: Dict[str, Dict[str, float]] = {}
        
        self.stock_history_daily: Dict[str, Dict[str, np.ndarray]] = {}  # Sym -> {H,L,C,V}
        self.stock_history_5m: Dict[str, Dict[str, np.ndarray]] = {}  # Sym -> {close, volume}
        self.history_loaded = False

        # Current Market State
        self.nifty_ltp = 0.0
        self.vix_ltp = 0.0
        self.nifty_pct = 0.0
        self.nifty_prev_close = 0.0  # V5: Store Nifty's previous close
        self.sector_scores: List[SectorScore] = []
        self.active_signals: List[StockSignal] = []
        self.last_quotes: Dict[str, Any] = {}
        
        # Cooldown for rejected symbols (Symbol -> Timestamp)
        self.rejected_symbols: Dict[str, float] = {}
        
        # Signal Handlers
        signal.signal(signal.SIGINT, self.shutdown)

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        self.logs.append(entry)
        logger.info(msg)

    def load_universe(self):
        """Load and validate the universe.json."""
        self.log("📂 Loading Universe...")
        if not config.UNIVERSE_PATH.exists():
            self.log("❌ universe.json not found!")
            sys.exit(1)
            
        with open(config.UNIVERSE_PATH, 'r') as f:
            data = json.load(f)
            self.indices = data.get('indices', [])
            self.stocks = [s for s in data.get('stocks', []) if s.get('token')]
            
        # Build Sector Map
        for s in self.stocks:
            for sector in s.get('indices', []):
                if sector not in self.sector_map:
                    self.sector_map[sector] = []
                self.sector_map[sector].append(s['symbol'])
        
        self.log(f"✅ Loaded {len(self.stocks)} stocks in {len(self.sector_map)} sectors.")

    def _filter_incomplete_candle(self, candles: List[Dict], interval_minutes: int = 5) -> List[Dict]:
        """
        Removes the last candle if it is incomplete (forming).
        Logic: If (Now - LastCandleTime) < interval_minutes, it's likely incomplete.
        """
        if not candles:
            return []

        last_candle = candles[-1]
        last_time = last_candle.get('date')

        # Kite historical data usually returns naive datetime objects in IST.
        # datetime.now() returns naive local time.
        now = datetime.now()

        # Calculate difference
        if isinstance(last_time, datetime):
             # Handle Timezone Mismatch
             # Kite API returns timezone-aware datetimes (e.g., +05:30)
             # datetime.now() returns naive datetime
             # We must strip timezone from Kite data to compare safely
             if last_time.tzinfo is not None:
                 last_time = last_time.replace(tzinfo=None)
             
             # Check if the candle is too recent
             time_diff = now - last_time
             if time_diff.total_seconds() < interval_minutes * 60:
                 # It's too recent, likely forming. Return all except last.
                 return candles[:-1]

        return candles

    def fetch_history(self):
        """Fetch historical data for Nifty and Sectors."""
        self.log("📉 Fetching Historical Data (Nifty + Sectors)...")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=45)
        
        # 1. Nifty 50
        nifty_token = 256265
        nifty_data = data_manager.get_historical(nifty_token, from_date, to_date, "day")
        if nifty_data:
            self.nifty_history = [d['close'] for d in nifty_data]
            
        # 2. Sectors
        for idx in self.indices:
            name = idx['name']
            if name in ["NIFTY 50", "INDIA VIX"]:
                continue
            
            token = data_manager.get_token(f"NSE:{idx['symbol']}")
            if token:
                data = data_manager.get_historical(token, from_date, to_date, "day")
                if data:
                    self.sector_history[idx['symbol']] = [d['close'] for d in data]
        
        self.history_loaded = True
        self.log(f"✅ History loaded for {len(self.sector_history)} sectors.")

    def fetch_stock_history(self, symbols: List[str]):
        """Fetch daily and 5m history for active symbols."""
        if not symbols:
            return
        
        self.log(f"📥 Fetching history for {len(symbols)} stocks...")
        to_date = datetime.now()
        from_date_daily = to_date - timedelta(days=config.LOOKBACK_DAYS_DAILY)
        from_date_5m = to_date - timedelta(days=config.LOOKBACK_DAYS_INTRA)
        
        for sym in symbols:
            token = data_manager.get_token(f"NSE:{sym}")
            if not token:
                continue
            
            # Daily History
            d_data = data_manager.get_historical(token, from_date_daily, to_date, "day")
            if d_data:
                self.stock_history_daily[sym] = {
                    'high': np.array([d['high'] for d in d_data]),
                    'low': np.array([d['low'] for d in d_data]),
                    'close': np.array([d['close'] for d in d_data]),
                    'volume': np.array([d['volume'] for d in d_data])
                }
            
            # 5m History
            raw_m_data = data_manager.get_historical(token, from_date_5m, to_date, "5minute")
            m_data = self._filter_incomplete_candle(raw_m_data)
            if m_data:
                self.stock_history_5m[sym] = {
                    'close': np.array([d['close'] for d in m_data]),
                    'volume': np.array([d['volume'] for d in m_data])
                }

    def _refresh_intraday_history(self, symbols: List[str]):
        """
        V5 FIX: Periodic re-fetch of 5-minute candles to keep RVOL/HMA fresh.
        Called every INTRADAY_REFRESH_INTERVAL_SEC (5 minutes).
        """
        if not symbols:
            return
        
        self.log(f"🔄 Refreshing 5m history for {len(symbols)} stocks...")
        to_date = datetime.now()
        from_date_5m = to_date - timedelta(days=config.LOOKBACK_DAYS_INTRA)
        
        refreshed_count = 0
        for sym in symbols:
            token = data_manager.get_token(f"NSE:{sym}")
            if not token:
                continue
            
            # Re-fetch 5m History
            raw_m_data = data_manager.get_historical(token, from_date_5m, to_date, "5minute")
            m_data = self._filter_incomplete_candle(raw_m_data)
            if m_data:
                self.stock_history_5m[sym] = {
                    'close': np.array([d['close'] for d in m_data]),
                    'volume': np.array([d['volume'] for d in m_data])
                }
                refreshed_count += 1
        
        self.log(f"✅ Refreshed 5m history for {refreshed_count} stocks.")

    def _get_hma_alignment(self, sym: str, current_price: float) -> str:
        """Calculate 3-layer HMA alignment (Position + Slope)."""
        daily = self.stock_history_daily.get(sym)
        m5 = self.stock_history_5m.get(sym)
        
        if daily is None or m5 is None:
            return "MIXED"
        
        # 1. Prepare Price Series
        closes_d = np.append(daily['close'], current_price)
        closes_5m = np.append(m5['close'], current_price)
        
        # 2. Calculate HMA Values
        # Tactical Trend: HMA 9 (Daily)
        hma9_curr = ind.calculate_hma(closes_d, 9)
        hma9_prev = ind.calculate_hma(closes_d[:-1], 9)
        
        hma20_curr = ind.calculate_hma(closes_5m, 20)
        hma20_prev = ind.calculate_hma(closes_5m[:-1], 20)
        
        # 3. Determine Alignment (Position AND Slope)
        h9_bull = (current_price > hma9_curr and ind.calculate_slope(hma9_curr, hma9_prev) == "UP")
        h20_bull = (current_price > hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "UP")
        
        h9_bear = (current_price < hma9_curr and ind.calculate_slope(hma9_curr, hma9_prev) == "DOWN")
        h20_bear = (current_price < hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "DOWN")
        
        if h9_bull and h20_bull:
            return "BULLISH"
        if h9_bear and h20_bear:
            return "BEARISH"
        return "MIXED"

    def _calculate_baselines(self):
        """
        V5 FIX: Pre-calculate anchor prices using Previous Close (ohlc.close).
        This ensures percentage calculations match broker terminals.
        """
        self.log("⚓ Calculating Baselines (Previous Close Anchor)...")
        
        # 1. Nifty Baselines
        if len(self.nifty_history) >= 20:
            self.baselines['NIFTY 50'] = {
                'close_20d': self.nifty_history[-20],
                'close_3d': self.nifty_history[-3],
                'prev_close': self.nifty_history[-1]  # V5: This is the key anchor
            }
            self.nifty_prev_close = self.nifty_history[-1]
            
        # 2. Sector Baselines
        for sym, hist in self.sector_history.items():
            if len(hist) >= 20:
                self.baselines[sym] = {
                    'close_20d': hist[-20],
                    'close_3d': hist[-3],
                    'prev_close': hist[-1]  # V5: Previous Close as anchor
                }

    def _fetch_initial_quotes(self):
        """
        V5 FIX: Fetch initial quotes to get Previous Close (ohlc.close) from API.
        This provides the "Golden Anchor" for all percentage calculations.
        """
        self.log("🎯 Fetching Initial Quotes (Golden Anchor)...")
        
        # Build list of all symbols we need
        all_symbols = ["NIFTY 50", "INDIA VIX"]
        all_symbols.extend([i['symbol'] for i in self.indices if i['name'] not in ["NIFTY 50", "INDIA VIX"]])
        
        # Fetch quotes in batches if needed (Kite allows 500 per call)
        quotes = data_manager.get_quote(all_symbols)
        
        # Update baselines with API's ohlc.close (Previous Close)
        for sym_key, quote_data in quotes.items():
            sym = sym_key.replace("NSE:", "")
            ohlc = quote_data.get('ohlc', {})
            prev_close = ohlc.get('close', 0)
            
            if prev_close > 0:
                if sym not in self.baselines:
                    self.baselines[sym] = {}
                self.baselines[sym]['prev_close'] = prev_close
                
                if sym == "NIFTY 50":
                    self.nifty_prev_close = prev_close
        
        self.log(f"✅ Fetched anchors for {len(quotes)} symbols.")

    def initialize(self):
        """Startup sequence."""
        self.log("🚀 Initializing V5 Bot...")
        
        # 1. Connect Data
        if not data_manager.connect():
            self.log("❌ Connection Failed.")
            sys.exit(1)
            
        # 2. Load Instruments & Universe
        data_manager.load_instruments()
        self.load_universe()

        # 3. Load State
        if self.state_mgr.load_state():
            self.state_mgr.restore_system(self.risk, self.lifecycle, self.orders)
            if self.risk.state.equity <= 0:
                self.risk.state.equity = 1000000.0
            self.log(f"✅ State Restored. Equity: ₹{self.risk.state.equity:,.0f}")
        else:
            self.log("🆕 Starting Fresh Session.")
            self.risk.update_account(1000000.0, 0.0, [])

        # 4. Fetch Historical VIX for Percentiles
        self.log("📈 Fetching VIX history...")
        vix_token = 264969
        hist = data_manager.get_historical(vix_token, datetime.now() - timedelta(days=config.LOOKBACK_DAYS_VIX), datetime.now(), "day")
        self.vix_history = [d['close'] for d in hist]
        
        # 5. Fetch Sector History & Baselines
        self.fetch_history()
        self._calculate_baselines()
        
        # 6. V5 FIX: Fetch Initial Quotes for Golden Anchor (Previous Close)
        self._fetch_initial_quotes()
        
        # 7. Start WebSocket for All Required Tokens
        all_tokens = [256265, 264969]  # Nifty, Vix
        all_tokens.extend([data_manager.get_token(f"NSE:{i['symbol']}") for i in self.indices if i['token']])
        all_tokens.extend([int(s['token']) for s in self.stocks if s.get('token')])
        
        valid_tokens = [t for t in all_tokens if t]
        data_manager.start_ticker(valid_tokens, on_ticks=None, mode="full")
        
        self.log(f"📡 WebSocket Started for {len(valid_tokens)} instruments.")
        self.log("✅ System Ready.")

    def get_playbook(self, now: dt_time) -> str:
        if now < config.MARKET_OPEN_TIME:
            return "PRE_MARKET"
        if now < config.OR_START_TIME:
            return "WAIT"
        if now < config.OR_END_TIME:
            return "OR_FORMATION"
        if now < config.GAP_START_TIME:
            return "ORB"
        if now < config.GAP_END_TIME:
            return "GAP"
        if now < config.ENTRY_CUTOFF_TIME:
            return "MAIN"
        if now < config.FORCE_EXIT_TIME:
            return "EXIT_ONLY"
        return "FORCE_EXIT"

    def _update_sector_ranks(self, quotes: Dict, nifty_quote: Dict, regime: str):
        """
        V5 FIX: Calculate rank-based sector scores using Previous Close as anchor.
        This ensures Daily Change and Daily RS reflect true daily performance.
        """
        new_scores = []
        
        if len(self.nifty_history) < 20:
            return
        
        # Use Live Ticks if available, else REST quote
        nifty_tick = data_manager.live_ticks.get(256265, {})
        nifty_ltp = nifty_tick.get('last_price', nifty_quote.get('last_price', 0))
        
        # V5 FIX: Use Previous Close as anchor instead of Open
        nifty_prev_close = self.baselines.get('NIFTY 50', {}).get('prev_close', 0)
        nifty_hist_20 = self.nifty_history[-20]
        nifty_hist_3 = self.nifty_history[-3]
        
        if nifty_hist_20 == 0 or nifty_hist_3 == 0 or nifty_prev_close == 0:
            return

        nifty_20d_ret = (nifty_ltp - nifty_hist_20) / nifty_hist_20 if nifty_hist_20 != 0 else 0.0
        nifty_3d_ret = (nifty_ltp - nifty_hist_3) / nifty_hist_3 if nifty_hist_3 != 0 else 0.0
        # V5 FIX: Daily return uses Previous Close
        nifty_daily_ret = (nifty_ltp - nifty_prev_close) / nifty_prev_close if nifty_prev_close > 0 else 0.0
        
        for idx in self.indices:
            name = idx['name']
            symbol = idx['symbol']
            if name in ["NIFTY 50", "INDIA VIX"]:
                continue
            
            # Use Live Ticks for Sector Price
            token = data_manager.get_token(f"NSE:{symbol}")
            tick = data_manager.live_ticks.get(token, {})
            q = quotes.get(f"NSE:{symbol}", {})
            
            curr = tick.get('last_price', q.get('last_price', 0))
            
            # V5 FIX: Get Previous Close from baselines
            sec_base = self.baselines.get(symbol, {})
            sec_prev_close = sec_base.get('prev_close', 0)
            
            # Historical Data Check
            hist = self.sector_history.get(symbol, [])
            if len(hist) < 20:
                continue
            
            hist_20 = hist[-20]
            hist_3 = hist[-3]
            if hist_20 == 0 or hist_3 == 0 or sec_prev_close == 0:
                continue

            # A. Calculate RS Components
            sec_20d_ret = (curr - hist_20) / hist_20 if hist_20 != 0 else 0.0
            sec_3d_ret = (curr - hist_3) / hist_3 if hist_3 != 0 else 0.0
            # V5 FIX: Daily return uses Previous Close
            sec_daily_ret = (curr - sec_prev_close) / sec_prev_close if sec_prev_close > 0 else 0.0
            
            # Subtraction Method
            struct_rs = (sec_20d_ret - nifty_20d_ret) * 100
            short_rs = (sec_3d_ret - nifty_3d_ret) * 100
            # V5 FIX: This is now Daily RS (not just Intraday)
            daily_rs = (sec_daily_ret - nifty_daily_ret) * 100
            
            # B. Calculate Breadth (Net: Bull% - Bear%)
            constituents = self.sector_map.get(name, [])
            valid_stocks = 0
            above_vwap = 0
            below_vwap = 0
            
            for sym in constituents:
                stk_token = data_manager.get_token(f"NSE:{sym}")
                stk_tick = data_manager.live_ticks.get(stk_token)
                
                if stk_tick and stk_tick.get('average_price', 0) > 0:
                    valid_stocks += 1
                    if stk_tick['last_price'] > stk_tick['average_price']:
                        above_vwap += 1
                    elif stk_tick['last_price'] < stk_tick['average_price']:
                        below_vwap += 1
            
            if valid_stocks > 0:
                net_breadth = (above_vwap / valid_stocks) - (below_vwap / valid_stocks)
            else:
                net_breadth = 0.0
            
            # Populate Score
            score = SectorScore(
                symbol=symbol,
                price=curr,
                change_pct=sec_daily_ret * 100,  # V5: Now Daily Change
                structural_rs=struct_rs,
                shortterm_rs=short_rs,
                intraday_rs=daily_rs,  # V5: Now Daily RS
                breadth=net_breadth
            )
            new_scores.append(score)
            
        self.sector_scores = self.sector_scorer.score_all(new_scores, regime, self.nifty_pct)
        self.sector_scorer.select_top_n(self.sector_scores)

    def _scan_tradeable_stocks(self, regime: str, vix_ltp: float):
        """Grade stocks in selected sectors and check entry with REAL data."""
        selected_sector_symbols = [s.symbol for s in self.sector_scores if s.is_selected]
        if not selected_sector_symbols:
            return
        
        # 1. Map symbols to their composite scores and ranks for easy lookup
        sector_info = {s.symbol: s for s in self.sector_scores}
        
        # 2. Collect all symbols in selected sectors
        all_candidate_symbols = []
        for sec_sym in selected_sector_symbols:
            sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
            if sec_name:
                all_candidate_symbols.extend(self.sector_map.get(sec_name, []))
        
        # Force-add Active Positions to scan list
        for active_sym in self.risk.state.active_symbols:
            if active_sym not in all_candidate_symbols:
                all_candidate_symbols.append(active_sym)
            
        # 3. Fetch History for new symbols (one-time fetch)
        missing_hist = [s for s in all_candidate_symbols if s not in self.stock_history_daily]
        if missing_hist:
            self.fetch_stock_history(missing_hist)
            
        can_enter = self.current_playbook in ["ORB", "MAIN"]
        
        self.active_signals = []
        for symbol in all_candidate_symbols:
            token = data_manager.get_token(f"NSE:{symbol}")
            tick = data_manager.live_ticks.get(token)
            hist = self.stock_history_daily.get(symbol)
            
            if not tick or not hist:
                continue
            
            # A0. Liquidity Filter (ADV check)
            adv = ExecutionFilters.calculate_adv_crores(hist['close'], hist['volume'])
            if adv < config.MIN_ADV_CRORES:
                continue

            curr_p = tick['last_price']
            
            # A. Calculate ATR (10-period Daily)
            atr = ind.calculate_atr(hist['high'], hist['low'], hist['close'], 10)
            if atr <= 0:
                continue
            
            # B. Microstructure Gate
            passed, reason = ExecutionFilters.check_gate(
                self.current_playbook, 
                tick.get('depth', {}).get('buy', [{}])[0].get('price', 0),
                tick.get('depth', {}).get('sell', [{}])[0].get('price', 0),
                curr_p, atr, 
                tick.get('upper_circuit_limit', 0), tick.get('lower_circuit_limit', 0)
            )
            
            # C. Indicators
            hma_align = self._get_hma_alignment(symbol, curr_p)
            stoch_k, _ = ind.calculate_stoch_rsi(np.append(hist['close'], curr_p))
            
            # RVOL Calculation (V5: Uses fresh 5m data from periodic refresh)
            hist_5m = self.stock_history_5m.get(symbol)
            if hist_5m and len(hist_5m['volume']) >= 20:
                recent_vols = hist_5m['volume'][-20:]
                avg_vol_20 = np.mean(recent_vols)
                last_closed_vol = hist_5m['volume'][-1]
                
                if avg_vol_20 > 0:
                    rvol = ind.calculate_rvol(last_closed_vol, avg_vol_20)
                else:
                    rvol = 0.0
            else:
                rvol = 0.0
            
            # D. Signal Grading
            stock_sector_name = next((sec for sec, syms in self.sector_map.items() if symbol in syms), "")
            stock_sector_sym = next((i['symbol'] for i in self.indices if i['name'] == stock_sector_name), "")
            
            sec_score_obj = sector_info.get(stock_sector_sym)
            sec_rank = sec_score_obj.rank if sec_score_obj else 16
            sec_bias = sec_score_obj.bias if sec_score_obj else "NEUTRAL"
            
            bid = tick.get('depth', {}).get('buy', [{}])[0].get('price', 0)
            ask = tick.get('depth', {}).get('sell', [{}])[0].get('price', 0)
            spread_atr = (ask - bid) / atr if (ask > 0 and bid > 0 and atr > 0) else 1.0
            
            signal = self.stock_grader.calculate_grade(
                hma_align=hma_align,
                rvol=rvol,
                stoch_k=stoch_k,
                sector_rank=sec_rank,
                spread_atr=spread_atr,
                playbook=self.current_playbook,
                vix_pctl=self.vix_percentile
            )
            
            # DIRECTIONAL FILTER
            if sec_bias == "LONG" and signal.direction != "LONG":
                signal.grade = "C"
                signal.reasons.append(f"Sector Bias LONG vs Signal {signal.direction}")
            elif sec_bias == "SHORT" and signal.direction != "SHORT":
                signal.grade = "C"
                signal.reasons.append(f"Sector Bias SHORT vs Signal {signal.direction}")
            elif sec_bias == "NEUTRAL":
                signal.grade = "C"
                signal.reasons.append("Sector Bias NEUTRAL")

            signal.symbol = symbol
            signal.sector = stock_sector_name
            signal.price = curr_p
            
            # V5 FIX: Calculate change using Previous Close
            # Get stock's previous close from ohlc in tick or from baselines
            stock_prev_close = tick.get('ohlc', {}).get('close', 0)
            if stock_prev_close > 0:
                signal.change_pct = ((curr_p - stock_prev_close) / stock_prev_close * 100)
            else:
                signal.change_pct = 0.0
            
            signal.gate_passed = passed
            signal.gate_reason = reason
            
            # 1. VISIBILITY: Add ALL signals to UI
            self.active_signals.append(signal)
            
            # 2. EXECUTION: Only Trade A+/A that passed the Gate
            if signal.grade in ["A+", "A"] and passed:
                if can_enter:
                    self._process_entry(signal, curr_p, atr)

    def _process_entry(self, signal: StockSignal, ltp: float, atr: float):
        """Handle Risk checks and lifecycle initiation."""
        # 0. Check Rejection Cooldown (5 mins)
        if signal.symbol in self.rejected_symbols:
            if time.time() - self.rejected_symbols[signal.symbol] < 300:
                return
            else:
                del self.rejected_symbols[signal.symbol]

        # Check Portfolio Limits
        allowed, reason = self.risk.can_open_new_trade(signal.symbol, signal.sector)
        if not allowed:
            return
            
        # Calculate Stop
        stop_mult = config.STOP_ATR_MULT_ORB if self.current_playbook == "ORB" else config.STOP_ATR_MULT_MAIN
        stop_dist = atr * stop_mult
        stop_price = ltp - stop_dist if signal.direction == "LONG" else ltp + stop_dist
        
        sizing = self.risk.calculate_position_size(
            ltp, stop_price, signal.grade, self.vix_multiplier, datetime.now().time()
        )
        
        if sizing.is_allowed:
            self.log(f"🔥 ENTERING {signal.symbol} ({signal.grade}) Qty: {sizing.shares}")
            trade_id = self.lifecycle.initiate_trade(
                signal.symbol, signal.direction, sizing.shares, ltp, stop_price, atr=atr, sector=signal.sector
            )
            
            if trade_id:
                self.risk.state.active_symbols.append(signal.symbol)
                self.risk.state.open_positions_count += 1
                self.risk.state.sector_exposure[signal.sector] = self.risk.state.sector_exposure.get(signal.sector, 0) + 1
        else:
            self.log(f"⚠️ Size Rejected {signal.symbol}: {sizing.reason}")
            self.rejected_symbols[signal.symbol] = time.time()

    def _recalculate_live_metrics(self):
        """
        V5 REFINED: High-speed recalculation using live WebSocket buffer.
        Uses Previous Close as anchor for all percentage calculations.
        """
        # 1. Get Live Nifty & Vix
        nifty_tick = data_manager.live_ticks.get(256265, {})
        vix_tick = data_manager.live_ticks.get(264969, {})
        
        self.nifty_ltp = nifty_tick.get('last_price', self.nifty_ltp)
        self.vix_ltp = vix_tick.get('last_price', self.vix_ltp)
        
        n_base = self.baselines.get('NIFTY 50', {})
        if not n_base or self.nifty_ltp == 0:
            return
        
        n_c20 = n_base.get('close_20d', 0)
        n_c3 = n_base.get('close_3d', 0)
        # V5 FIX: Use Previous Close as anchor
        n_prev_close = n_base.get('prev_close', 0)
        if n_c20 == 0 or n_c3 == 0 or n_prev_close == 0:
            return

        n_ret_20d = (self.nifty_ltp - n_c20) / n_c20 if n_c20 != 0 else 0.0
        n_ret_3d = (self.nifty_ltp - n_c3) / n_c3 if n_c3 != 0 else 0.0
        # V5 FIX: Daily return based on Previous Close
        n_ret_daily = (self.nifty_ltp - n_prev_close) / n_prev_close if n_prev_close > 0 else 0.0
        self.nifty_pct = n_ret_daily * 100

        # 2. Update Sectors
        for s in self.sector_scores:
            token = data_manager.get_token(f"NSE:{s.symbol}")
            tick = data_manager.live_ticks.get(token, {})
            if not tick:
                continue
            
            base = self.baselines.get(s.symbol, {})
            if not base:
                continue
            
            s.price = tick.get('last_price', s.price)
            
            s_c20 = base.get('close_20d', 0)
            s_c3 = base.get('close_3d', 0)
            # V5 FIX: Use Previous Close
            s_prev_close = base.get('prev_close', 0)
            
            if s_c20 == 0 or s_c3 == 0 or s_prev_close == 0:
                continue

            # Real-time RS
            s_ret_20d = (s.price - s_c20) / s_c20 if s_c20 != 0 else 0.0
            s_ret_3d = (s.price - s_c3) / s_c3 if s_c3 != 0 else 0.0
            # V5 FIX: Daily return based on Previous Close
            s_ret_daily = (s.price - s_prev_close) / s_prev_close if s_prev_close > 0 else 0.0
            
            s.structural_rs = (s_ret_20d - n_ret_20d) * 100
            s.shortterm_rs = (s_ret_3d - n_ret_3d) * 100
            s.intraday_rs = (s_ret_daily - n_ret_daily) * 100  # V5: Now Daily RS
            s.change_pct = s_ret_daily * 100  # V5: Now Daily Change
            
            # Real-time Breadth
            constituents = self.sector_map.get(next((i['name'] for i in self.indices if i['symbol'] == s.symbol), ""), [])
            valid = 0
            above = 0
            below = 0
            for sym in constituents:
                stk_token = data_manager.get_token(f"NSE:{sym}")
                stk_tick = data_manager.live_ticks.get(stk_token, {})
                if stk_tick and stk_tick.get('average_price', 0) > 0:
                    valid += 1
                    if stk_tick['last_price'] > stk_tick['average_price']:
                        above += 1
                    elif stk_tick['last_price'] < stk_tick['average_price']:
                        below += 1
            
            if valid > 0:
                s.breadth = (above / valid) - (below / valid)

        # 3. Re-Score & Sort
        regime = self.regime_detector.get_regime(self.vix_percentile)
        self.sector_scores = self.sector_scorer.score_all(self.sector_scores, regime, self.nifty_pct)
        self.sector_scorer.select_top_n(self.sector_scores)

    def run(self):
        """Main Loop."""
        self.initialize()
        
        # Initial market data fetch
        quote_symbols = ["NIFTY 50", "INDIA VIX"]
        quote_symbols.extend([i['symbol'] for i in self.indices if i['name'] != "NIFTY 50" and i['name'] != "INDIA VIX"])
        market_quotes = data_manager.get_quote(quote_symbols)
        self.last_quotes.update(market_quotes)
        
        nifty_quote = market_quotes.get("NSE:NIFTY 50", {})
        regime = self.regime_detector.get_regime(self.vix_percentile)
        self._update_sector_ranks(market_quotes, nifty_quote, regime)
        
        with Live(self.ui.render(), refresh_per_second=4, screen=True) as live:
            while self.running:
                try:
                    now_dt = datetime.now()
                    self.current_playbook = self.get_playbook(now_dt.time())
                    
                    # 1. V5 FIX: Periodic 5m history refresh for RVOL/HMA
                    if time.time() - self.last_intraday_refresh >= config.INTRADAY_REFRESH_INTERVAL_SEC:
                        # Get list of symbols to refresh (selected sectors + active positions)
                        refresh_symbols = []
                        for s in self.sector_scores:
                            if s.is_selected:
                                sec_name = next((i['name'] for i in self.indices if i['symbol'] == s.symbol), None)
                                if sec_name:
                                    refresh_symbols.extend(self.sector_map.get(sec_name, []))
                        refresh_symbols.extend(self.risk.state.active_symbols)
                        refresh_symbols = list(set(refresh_symbols))  # Deduplicate
                        
                        if refresh_symbols:
                            self._refresh_intraday_history(refresh_symbols)
                        self.last_intraday_refresh = time.time()
                    
                    # 2. High-Speed Metrics Recalculation (Every UI_REFRESH_INTERVAL)
                    if time.time() - self.last_ui_update >= config.UI_REFRESH_INTERVAL:
                        self._recalculate_live_metrics()
                        
                        # Update VIX metrics
                        self.vix_percentile = self.regime_detector.calculate_percentile(self.vix_ltp, self.vix_history)
                        self.vix_multiplier = self.regime_detector.get_vix_multiplier(self.vix_percentile)
                        
                        # Safety check
                        self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
                        if self.safety.is_halted:
                            self.log(f"🛑 HALTED: {self.safety.halt_reason}")
                            self.lifecycle.force_exit_all()
                        else:
                            # Scan for signals
                            self._scan_tradeable_stocks(
                                self.regime_detector.get_regime(self.vix_percentile),
                                self.vix_ltp
                            )
                        
                        self.last_ui_update = time.time()
                    
                    # 3. Update Lifecycle (Exits/Trailing) - FASTER than UI
                    active_trades_data = {}
                    for trade in self.lifecycle.trades.values():
                        if trade.stage != "CLOSED":
                            token = data_manager.get_token(f"NSE:{trade.symbol}")
                            tick = data_manager.live_ticks.get(token)
                            if tick:
                                active_trades_data[f"NSE:{trade.symbol}"] = tick
                    
                    if active_trades_data:
                        self.lifecycle.update_trades(active_trades_data)
                    
                    # 4. Force Exit Check
                    if self.current_playbook == "FORCE_EXIT":
                        self.lifecycle.force_exit_all()
                    
                    # 5. Periodic Sync
                    if int(time.time()) % 60 == 0:
                        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                    
                    # 6. UI Render State
                    positions_for_ui = []
                    total_unrealized_pnl = 0.0
                    for pos in self.orders.get_positions():
                        sym = pos['symbol']
                        token = data_manager.get_token(f"NSE:{sym}")
                        tick = data_manager.live_ticks.get(token, {})
                        ltp = tick.get('last_price', pos['entry_price'])
                        
                        upnl = (ltp - pos['entry_price']) * pos['qty']
                        pos['unrealized_pnl'] = upnl
                        pos['ltp'] = ltp
                        total_unrealized_pnl += upnl
                        
                        trade_data = next((t for t in self.lifecycle.trades.values() 
                                         if t.symbol == sym and t.stage != "CLOSED"), None)
                        
                        if trade_data:
                            pos['current_stop'] = trade_data.current_stop
                            pos['target'] = trade_data.target_1 if trade_data.stage == "ACTIVE" else "Run"
                            pos['stage'] = trade_data.stage
                        else:
                            pos['current_stop'] = 0.0
                            pos['target'] = 0.0
                            pos['stage'] = "MANUAL"

                        positions_for_ui.append(pos)

                    current_equity = max(self.risk.state.equity, config.DEFAULT_PAPER_EQUITY)
                    self.risk.update_account(
                        current_equity,
                        self.risk.state.current_pnl, 
                        positions_for_ui
                    )

                    ui_state = {
                        "session": self.current_playbook,
                        "regime": self.regime_detector.get_regime(self.vix_percentile),
                        "vix": self.vix_ltp,
                        "nifty": self.nifty_ltp,
                        "nifty_pct": self.nifty_pct,
                        "sectors": self.sector_scores,
                        "signals": self.active_signals,
                        "positions": positions_for_ui,
                        "equity": self.risk.state.equity + total_unrealized_pnl,
                        "pnl": self.risk.state.current_pnl + total_unrealized_pnl,
                        "logs": self.logs
                    }
                    self.ui.update(ui_state)
                    live.update(self.ui.render())
                    
                    time.sleep(0.5)
                    
                except Exception as e:
                    self.log(f"🔥 LOOP ERROR: {e}")
                    self.log(f"🔥 TRACEBACK: {traceback.format_exc()}")
                    time.sleep(5)

    def shutdown(self, sig, frame):
        self.log("🛑 Shutdown Signal Received.")
        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
        self.running = False
        sys.exit(0)


if __name__ == "__main__":
    bot = TradingBotV5()
    bot.run()
