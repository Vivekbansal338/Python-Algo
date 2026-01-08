"""
================================================================================
V4 ORCHESTRATOR (MAIN) - REFINED
================================================================================
The Master Controller. Integrates:
Data -> Strategy -> Signal -> Risk -> Order -> Lifecycle -> UI -> Persistence

Strictly enforces Playbook Timing and Safety Checks.

Author: Sector Analysis System
Version: 4.0.0
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

from core_v4 import config_v4 as config
from core_v4.data_v4 import data_manager
from analysis_v4.strategy_v4 import (
    MarketRegimeDetector, SectorScorer, SectorScore, 
    StockGrader, StockSignal, ExecutionFilters
)
from analysis_v4 import indicators_v4 as ind
from execution_v4.risk_v4 import RiskManager
from execution_v4.orders_v4 import OrderManager
from execution_v4.lifecycle_v4 import LifecycleManager
from system_v4.state_v4 import StateManager
from system_v4.ui_v4 import DashboardUI
from system_v4.safety_v4 import SafetyMonitor

# Logging to file ONLY
# We clear existing handlers to prevent console output
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

class TradingBotV4:
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
        self.sector_map: Dict[str, List[str]] = {} # Sector -> [Symbols]
        
        # Runtime Metrics
        self.logs = []
        self.current_playbook = "INIT"
        self.vix_percentile = 50.0
        self.vix_multiplier = 1.0
        self.vix_history: List[float] = []
        self.last_recalc_time = 0
        
        # Historical Data Cache
        self.sector_history: Dict[str, List[float]] = {} # Symbol -> [Closes]
        self.nifty_history: List[float] = [] # Nifty Closes
        self.baselines: Dict[str, Dict[str, float]] = {} # Sym -> {open, close_3d, close_20d}
        self.stock_history_daily: Dict[str, Dict[str, np.ndarray]] = {} # Sym -> {H,L,C,V}
        self.stock_history_5m: Dict[str, np.ndarray] = {} # Sym -> [Closes]
        self.history_loaded = False

        # Current Market State
        self.nifty_ltp = 0.0
        self.vix_ltp = 0.0
        self.nifty_pct = 0.0
        self.nifty_open = 0.0
        self.sector_scores: List[SectorScore] = []
        self.active_signals: List[StockSignal] = []
        self.last_quotes: Dict[str, Any] = {}
        self.last_ui_update = 0
        
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
            self.stocks = [s for s in data.get('stocks', []) if s.get('token')] # Filter empty tokens
            
        # Build Sector Map
        for s in self.stocks:
            for sector in s.get('indices', []):
                if sector not in self.sector_map:
                    self.sector_map[sector] = []
                self.sector_map[sector].append(s['symbol'])
        
        self.log(f"✅ Loaded {len(self.stocks)} stocks in {len(self.sector_map)} sectors.")

    def fetch_history(self):
        """Fetch historical data for Nifty and Sectors."""
        self.log("📉 Fetching Historical Data (Nifty + Sectors)...")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=45) # Buffer for 20 trading days
        
        # 1. Nifty 50
        nifty_token = 256265
        nifty_data = data_manager.get_historical(nifty_token, from_date, to_date, "day")
        if nifty_data:
            self.nifty_history = [d['close'] for d in nifty_data]
            
        # 2. Sectors
        for idx in self.indices:
            name = idx['name']
            if name in ["NIFTY 50", "INDIA VIX"]: continue
            
            token = data_manager.get_token(f"NSE:{idx['symbol']}")
            if token:
                data = data_manager.get_historical(token, from_date, to_date, "day")
                if data:
                    self.sector_history[idx['symbol']] = [d['close'] for d in data]
        
        self.history_loaded = True
        self.log(f"✅ History loaded for {len(self.sector_history)} sectors.")

    def fetch_stock_history(self, symbols: List[str]):
        """Fetch daily and 5m history for active symbols."""
        if not symbols: return
        
        self.log(f"📥 Fetching history for {len(symbols)} stocks...")
        to_date = datetime.now()
        from_date_daily = to_date - timedelta(days=60)
        from_date_5m = datetime.combine(to_date.date(), dt_time(9, 15))
        
        for sym in symbols:
            token = data_manager.get_token(f"NSE:{sym}")
            if not token: continue
            
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
            m_data = data_manager.get_historical(token, from_date_5m, to_date, "5minute")
            if m_data:
                self.stock_history_5m[sym] = np.array([d['close'] for d in m_data])

    def _get_hma_alignment(self, sym: str, current_price: float) -> str:
        """Calculate 3-layer HMA alignment (Position + Slope)."""
        daily = self.stock_history_daily.get(sym)
        m5 = self.stock_history_5m.get(sym)
        
        if daily is None or m5 is None: return "MIXED"
        
        # 1. Prepare Price Series
        closes_d = np.append(daily['close'], current_price)
        closes_5m = np.append(m5, current_price)
        
        # 2. Calculate HMA Values (Current & Previous for slope)
        # We need a small lookback for slopes
        # NOTE: HMA 40 (Daily) is commented out to increase responsiveness.
        # It was too slow for sharp reversals. We rely on Sector Bias for macro trend.
        # hma40_curr = ind.calculate_hma(closes_d, 40)
        # hma40_prev = ind.calculate_hma(closes_d[:-1], 40)
        
        hma16_curr = ind.calculate_hma(closes_d, 16)
        hma16_prev = ind.calculate_hma(closes_d[:-1], 16)
        
        hma20_curr = ind.calculate_hma(closes_5m, 20)
        hma20_prev = ind.calculate_hma(closes_5m[:-1], 20)
        
        # 3. Determine Alignment (Position AND Slope)
        # Bullish: Price > HMA AND Slope is UP
        # h40_bull = (current_price > hma40_curr and ind.calculate_slope(hma40_curr, hma40_prev) == "UP")
        h16_bull = (current_price > hma16_curr and ind.calculate_slope(hma16_curr, hma16_prev) == "UP")
        h20_bull = (current_price > hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "UP")
        
        # Bearish: Price < HMA AND Slope is DOWN
        # h40_bear = (current_price < hma40_curr and ind.calculate_slope(hma40_curr, hma40_prev) == "DOWN")
        h16_bear = (current_price < hma16_curr and ind.calculate_slope(hma16_curr, hma16_prev) == "DOWN")
        h20_bear = (current_price < hma20_curr and ind.calculate_slope(hma20_curr, hma20_prev) == "DOWN")
        
        if h16_bull and h20_bull: return "BULLISH" # Removed h40_bull check
        if h16_bear and h20_bear: return "BEARISH" # Removed h40_bear check
        return "MIXED"

    def _calculate_baselines(self):
        """Pre-calculate anchor prices for real-time RS."""
        self.log("⚓ Calculating Baselines...")
        
        # 1. Nifty Baselines
        if len(self.nifty_history) >= 20:
            self.baselines['NIFTY 50'] = {
                'close_20d': self.nifty_history[-20],
                'close_3d': self.nifty_history[-3],
                'prev_close': self.nifty_history[-1]
            }
            
        # 2. Sector Baselines
        for sym, hist in self.sector_history.items():
            if len(hist) >= 20:
                self.baselines[sym] = {
                    'close_20d': hist[-20],
                    'close_3d': hist[-3],
                    'prev_close': hist[-1]
                }

    def initialize(self):
        """Startup sequence."""
        self.log("🚀 Initializing V4 Bot...")
        
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
            # Safety: Ensure restored equity isn't zero
            if self.risk.state.equity <= 0:
                self.risk.state.equity = 1000000.0
            self.log(f"✅ State Restored. Equity: ₹{self.risk.state.equity:,.0f}")
        else:
            self.log("🆕 Starting Fresh Session.")
            self.risk.update_account(1000000.0, 0.0, []) # Default 10L start

        # 4. Fetch Historical VIX for Percentiles
        self.log("📈 Fetching VIX history...")
        vix_token = 264969 # INDIA VIX
        hist = data_manager.get_historical(vix_token, datetime.now() - timedelta(days=45), datetime.now(), "day")
        self.vix_history = [d['close'] for d in hist]
        
        # 5. Fetch Sector History & Baselines
        self.fetch_history()
        self._calculate_baselines()
        
        # 6. Start WebSocket for All Required Tokens
        all_tokens = [256265, 264969] # Nifty, Vix
        all_tokens.extend([data_manager.get_token(f"NSE:{i['symbol']}") for i in self.indices if i['token']])
        all_tokens.extend([int(s['token']) for s in self.stocks if s.get('token')])
        
        valid_tokens = [t for t in all_tokens if t]
        data_manager.start_ticker(valid_tokens, on_ticks=None, mode="full")
        
        self.log(f"📡 WebSocket Started for {len(valid_tokens)} instruments.")
        self.log("✅ System Ready.")

    def get_playbook(self, now: dt_time) -> str:
        if now < config.MARKET_OPEN_TIME: return "PRE_MARKET"
        if now < config.OR_START_TIME: return "WAIT"
        if now < config.OR_END_TIME: return "OR_FORMATION"
        if now < config.GAP_START_TIME: return "ORB"
        if now < config.GAP_END_TIME: return "GAP"
        if now < config.ENTRY_CUTOFF_TIME: return "MAIN"
        if now < config.FORCE_EXIT_TIME: return "EXIT_ONLY"
        return "FORCE_EXIT"

    def run_strategy_cycle(self):
        """Main Strategy Logic: Scan -> Score -> Signal."""
        now = datetime.now()
        
        # 1. Update Market Baseline (Nifty, VIX)
        quote_symbols = ["NIFTY 50", "INDIA VIX"]
        # Add all Sector symbols
        quote_symbols.extend([i['symbol'] for i in self.indices if i['name'] != "NIFTY 50" and i['name'] != "INDIA VIX"])
        
        market_quotes = data_manager.get_quote(quote_symbols)
        self.last_quotes.update(market_quotes)
        
        # Extract Nifty & VIX
        nifty_quote = market_quotes.get("NSE:NIFTY 50", {})
        vix_quote = market_quotes.get("NSE:INDIA VIX", {})
        
        self.nifty_ltp = nifty_quote.get('last_price', 0.0)
        self.vix_ltp = vix_quote.get('last_price', 0.0)
        
        # Calculate Nifty % change from open for UI
        n_open = nifty_quote.get('ohlc', {}).get('open', 0)
        self.nifty_pct = ((self.nifty_ltp - n_open) / n_open * 100) if n_open > 0 else 0.0
        
        if self.nifty_ltp == 0 or self.vix_ltp == 0: return # Wait for data
        
        # 2. Update Safety & Regime
        self.vix_percentile = self.regime_detector.calculate_percentile(self.vix_ltp, self.vix_history)
        regime = self.regime_detector.get_regime(self.vix_percentile)
        self.vix_multiplier = self.regime_detector.get_vix_multiplier(self.vix_percentile)
        
        # Mock red_stock_pct for safety update
        self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
        if self.safety.is_halted:
            self.log(f"🛑 HALTED: {self.safety.halt_reason}")
            self.lifecycle.force_exit_all()
            return

        # 3. Sector Scoring (Every 15 mins or session change)
        if time.time() - self.last_recalc_time > 900 or not self.sector_scores:
            self.last_recalc_time = time.time()
            self._update_sector_ranks(market_quotes, nifty_quote, regime)

        # 4. Stock Signaling
        self._scan_tradeable_stocks(regime, self.vix_ltp)

    def _update_sector_ranks(self, quotes: Dict, nifty_quote: Dict, regime: str):
        """Calculate rank-based sector scores with REAL RS and Breadth."""
        new_scores = []
        
        # 1. Nifty Returns (Benchmark)
        if len(self.nifty_history) < 20: 
            return
        
        # Use Live Ticks if available, else REST quote
        nifty_tick = data_manager.live_ticks.get(256265, {})
        nifty_ltp = nifty_tick.get('last_price', nifty_quote.get('last_price', 0))
        nifty_open = nifty_tick.get('ohlc', {}).get('open', nifty_quote.get('ohlc', {}).get('open', 0))
        
        # Guard Nifty history zeros
        nifty_hist_20 = self.nifty_history[-20]
        nifty_hist_3 = self.nifty_history[-3]
        if nifty_hist_20 == 0 or nifty_hist_3 == 0: 
            return

        nifty_20d_ret = (nifty_ltp - nifty_hist_20) / nifty_hist_20 if nifty_hist_20 != 0 else 0.0
        nifty_3d_ret = (nifty_ltp - nifty_hist_3) / nifty_hist_3 if nifty_hist_3 != 0 else 0.0
        nifty_intra_ret = (nifty_ltp - nifty_open) / nifty_open if nifty_open > 0 else 0.0
        
        for idx in self.indices:
            name = idx['name']
            symbol = idx['symbol']
            if name in ["NIFTY 50", "INDIA VIX"]: continue
            
            # Use Live Ticks for Sector Price
            token = data_manager.get_token(f"NSE:{symbol}")
            tick = data_manager.live_ticks.get(token, {})
            q = quotes.get(f"NSE:{symbol}", {})
            
            curr = tick.get('last_price', q.get('last_price', 0))
            o = tick.get('ohlc', {}).get('open', q.get('ohlc', {}).get('open', 0))
            
            # Historical Data Check
            hist = self.sector_history.get(symbol, [])
            if len(hist) < 20: 
                continue
            
            # Guard Sector history zeros
            hist_20 = hist[-20]
            hist_3 = hist[-3]
            if hist_20 == 0 or hist_3 == 0: 
                continue

            # A. Calculate RS Components
            sec_20d_ret = (curr - hist_20) / hist_20 if hist_20 != 0 else 0.0
            sec_3d_ret = (curr - hist_3) / hist_3 if hist_3 != 0 else 0.0
            sec_intra_ret = ((curr - o) / o) if o > 0 else 0.0
            
            # Subtraction Method
            struct_rs = (sec_20d_ret - nifty_20d_ret) * 100
            short_rs = (sec_3d_ret - nifty_3d_ret) * 100
            intra_rs = (sec_intra_ret - nifty_intra_ret) * 100
            
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
                change_pct=sec_intra_ret * 100,
                structural_rs=struct_rs,
                shortterm_rs=short_rs,
                intraday_rs=intra_rs,
                breadth=net_breadth
            )
            new_scores.append(score)
            
        self.sector_scores = self.sector_scorer.score_all(new_scores, regime)
        self.sector_scorer.select_top_n(self.sector_scores)

    def _scan_tradeable_stocks(self, regime: str, vix_ltp: float):
        """Grade stocks in selected sectors and check entry with REAL data."""
        selected_sector_symbols = [s.symbol for s in self.sector_scores if s.is_selected]
        if not selected_sector_symbols: return
        
        # 1. Map symbols to their composite scores and ranks for easy lookup
        sector_info = {s.symbol: s for s in self.sector_scores}
        
        # 2. Collect all symbols in selected sectors
        all_candidate_symbols = []
        for sec_sym in selected_sector_symbols:
            sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
            if sec_name:
                all_candidate_symbols.extend(self.sector_map.get(sec_name, []))
            
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
            
            if not tick or not hist: continue
            
            # A0. Liquidity Filter (ADV check)
            adv = ExecutionFilters.calculate_adv_crores(hist['close'], hist['volume'])
            if adv < config.MIN_ADV_CRORES:
                continue

            curr_p = tick['last_price']
            
            # A. Calculate ATR (10-period Daily)
            atr = ind.calculate_atr(hist['high'], hist['low'], hist['close'], 10)
            if atr <= 0: continue
            
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
            
            avg_vol = np.mean(hist['volume'][-20:])
            rvol = ind.calculate_rvol(tick.get('volume', 0), avg_vol)
            
            # D. Signal Grading
            # Get rank of the primary sector this stock belongs to
            stock_sector_name = next((sec for sec, syms in self.sector_map.items() if symbol in syms), "")
            stock_sector_sym = next((i['symbol'] for i in self.indices if i['name'] == stock_sector_name), "")
            
            # Retrieve Sector Info (Score, Rank, Bias)
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
            
            # DIRECTIONAL FILTER:
            # Only allow signals that match the Sector Bias
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
            
            open_pr = tick.get('ohlc', {}).get('open', 0)
            signal.change_pct = ((curr_p - open_pr) / open_pr * 100) if open_pr > 0 else 0.0
            signal.gate_passed = passed
            signal.gate_reason = reason
            
            # 1. VISIBILITY: Add ALL signals to UI (Sorted by score in UI)
            self.active_signals.append(signal)
            
            # 2. EXECUTION: Only Trade A+/A that passed the Gate
            if signal.grade in ["A+", "A"] and passed:
                # E. Risk & Entry
                if can_enter:
                    self._process_entry(signal, curr_p, atr)

    def _process_entry(self, signal: StockSignal, ltp: float, atr: float):
        """Handle Risk checks and lifecycle initiation."""
        # 0. Check Rejection Cooldown (5 mins)
        if signal.symbol in self.rejected_symbols:
            if time.time() - self.rejected_symbols[signal.symbol] < 300:
                return
            else:
                del self.rejected_symbols[signal.symbol] # Expired

        # Check Portfolio Limits
        allowed, reason = self.risk.can_open_new_trade(signal.symbol, signal.sector)
        if not allowed:
            return
            
        # Calculate Stop (Concept based)
        stop_mult = 2.4 if self.current_playbook == "ORB" else 2.0
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
                # IMMEDIATE STATE UPDATE to prevent double entry
                self.risk.state.active_symbols.append(signal.symbol)
                self.risk.state.open_positions_count += 1
                self.risk.state.sector_exposure[signal.sector] = self.risk.state.sector_exposure.get(signal.sector, 0) + 1
        else:
            self.log(f"⚠️ Size Rejected {signal.symbol}: {sizing.reason}")
            # Add to rejection cache
            self.rejected_symbols[signal.symbol] = time.time()

    def _recalculate_live_metrics(self):
        """High-speed recalculation using live WebSocket buffer."""
        # 1. Get Live Nifty & Vix
        nifty_tick = data_manager.live_ticks.get(256265, {})
        vix_tick = data_manager.live_ticks.get(264969, {})
        
        self.nifty_ltp = nifty_tick.get('last_price', self.nifty_ltp)
        self.vix_ltp = vix_tick.get('last_price', self.vix_ltp)
        
        n_base = self.baselines.get('NIFTY 50', {})
        if not n_base or self.nifty_ltp == 0: 
            return
        
        # Guard against zero baselines
        n_c20 = n_base.get('close_20d', 0)
        n_c3 = n_base.get('close_3d', 0)
        if n_c20 == 0 or n_c3 == 0: 
            return

        n_ret_20d = (self.nifty_ltp - n_c20) / n_c20 if n_c20 != 0 else 0.0
        n_ret_3d = (self.nifty_ltp - n_c3) / n_c3 if n_c3 != 0 else 0.0
        
        # Current Nifty Open from tick
        n_open = nifty_tick.get('ohlc', {}).get('open', self.nifty_open)
        self.nifty_open = n_open
        n_ret_intra = (self.nifty_ltp - n_open) / n_open if n_open > 0 else 0.0
        self.nifty_pct = n_ret_intra * 100

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
            s_open = tick.get('ohlc', {}).get('open', s.price)
            
            # Guard against zero baselines
            s_c20 = base.get('close_20d', 0)
            s_c3 = base.get('close_3d', 0)
            
            if s_c20 == 0 or s_c3 == 0: 
                continue

            # Real-time RS
            s_ret_20d = (s.price - s_c20) / s_c20 if s_c20 != 0 else 0.0
            s_ret_3d = (s.price - s_c3) / s_c3 if s_c3 != 0 else 0.0
            s_ret_intra = (s.price - s_open) / s_open if s_open > 0 else 0.0
            
            s.structural_rs = (s_ret_20d - n_ret_20d) * 100
            s.shortterm_rs = (s_ret_3d - n_ret_3d) * 100
            s.intraday_rs = (s_ret_intra - n_ret_intra) * 100
            s.change_pct = s_ret_intra * 100
            
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
        self.sector_scores = self.sector_scorer.score_all(self.sector_scores, regime)
        self.sector_scorer.select_top_n(self.sector_scores)

    def run(self):
        """Main Loop."""
        self.initialize()
        
        # Initial full strategy cycle
        self.run_strategy_cycle()
        
        with Live(self.ui.render(), refresh_per_second=4, screen=True) as live:
            while self.running:
                try:
                    now_dt = datetime.now()
                    self.current_playbook = self.get_playbook(now_dt.time())
                    
                    # 1. High-Speed Metrics Recalculation (Every Interval)
                    if time.time() - self.last_ui_update >= config.UI_REFRESH_INTERVAL:
                        self._recalculate_live_metrics()
                        
                        # Only run full strategy cycle (history fetch etc) occasionally
                        # or based on specific conditions. Here we rely on live ticks.
                        self._scan_tradeable_stocks(
                            self.regime_detector.get_regime(self.vix_percentile),
                            self.vix_ltp
                        )
                        self.last_ui_update = time.time()
                    
                    # 2. Update Lifecycle (Exits/Trailing) - FASTER than UI
                    # We need LTPs for all active trades from live_ticks
                    active_trades_data = {}
                    for trade in self.lifecycle.trades.values():
                        if trade.stage != "CLOSED":
                            token = data_manager.get_token(f"NSE:{trade.symbol}")
                            tick = data_manager.live_ticks.get(token)
                            if tick:
                                active_trades_data[f"NSE:{trade.symbol}"] = tick
                    
                    if active_trades_data:
                        self.lifecycle.update_trades(active_trades_data)
                    
                    # 3. Force Exit Check
                    if self.current_playbook == "FORCE_EXIT":
                        self.lifecycle.force_exit_all()
                    
                    # 4. Periodic Sync
                    if int(time.time()) % 60 == 0:
                        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                    
                    # 5. UI Render State
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
                        
                        # Enrich with Lifecycle Data (Stop, Target, Stage)
                        # Find matching active trade
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

                    # Update Risk State with actual positions
                    current_equity = max(self.risk.state.equity, 1000000.0)
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
                    
                    time.sleep(0.5) # Fast loop for lifecycle, UI throttled by last_ui_update
                    
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
    bot = TradingBotV4()
    bot.run()