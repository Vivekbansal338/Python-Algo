"""
===============================================================================
V6.8 SECTOR BACKTEST ENGINE — ENHANCED SIGNAL QUALITY GATES + BROKERAGE
===============================================================================
Inherits V6.6 A+-only policy + execution/risk/exit architecture, and adds
five signal-quality gates to eliminate low-conviction entries.

Also adds full brokerage/slippage accounting on every executed order leg
(entry, partial exit, and final exit), and persists charge breakdowns in
trade-level and run-level summaries.

SIGNAL QUALITY GATES (new in V6.7):
────────────────────────────────────
1) HMA SLOPE CONFIRMATION
   - Compute HMA(9) and HMA(21) slopes over the last SLOPE_LOOKBACK bars.
   - For LONG : both slopes must be positive (pointing up).
   - For SHORT: both slopes must be negative (pointing down).
   - Flat or counter-directional slopes → reject.

2) CROSSOVER FRESHNESS
   - Detect the exact bar where HMA(9) crossed HMA(21).
   - Only accept signals within CROSS_FRESHNESS_BARS of the crossover.
   - Stale crossovers (>N bars old) are rejected — the momentum is spent.

3) PRICE-HMA ALIGNMENT
   - For LONG : price must be above HMA(9) which must be above HMA(21).
   - For SHORT: price must be below HMA(9) which must be below HMA(21).
   - Price trapped between the two HMAs → no clean trend → reject.

4) HMA SEPARATION (Anti-Chop Filter)
   - HMA gap = abs(HMA9 − HMA21) must be at least MIN_HMA_SEP_ATR_FRAC
     times the 5-minute ATR.
   - Prevents entries during tight, choppy HMA convergence zones.

5) HMA DIVERGENCE (Momentum Expanding)
   - Current HMA gap must be wider than gap DIVERGENCE_LOOKBACK bars ago.
   - Ensures the fast HMA is accelerating *away* — momentum is expanding.
   - Converging HMAs (decelerating move) → reject.

Everything else — risk, sizing, stops, trailing, TP1, history export — is
identical to V6.6.
===============================================================================
"""

import argparse
import copy
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Enable `python backtest_v6/sector_engine_v6.8.py` from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v6 import config
from v6.brain import (
    ExecutionFilters,
    MarketRegimeDetector,
    RiskManager,
    SafetyMonitor,
    SectorScore,
    SectorScorer,
    StockSignal,
)
from v6.data_engine import (
    calculate_atr,
    calculate_hma,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SectorBacktesterV6")

# ═══════════════════════════════════════════════════════════════════════════════
# V6.1 INTRADAY RISK/TARGET CONFIGURATION (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

STOP_ATR_MULT_5M = 1.6
STOP_MIN_PCT = 0.0035

BE_ARM_R = 0.6
BE_BUFFER_BPS = 3

TRAIL_ARM_R = 0.8
TRAIL_LOOKBACK_BARS = 10
TRAIL_MULT_LOW = 2.2
TRAIL_MULT_MID = 1.8
TRAIL_MULT_HIGH = 1.4

# ═══════════════════════════════════════════════════════════════════════════════
# V6.7 SIGNAL QUALITY GATE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# HMA periods — change these to experiment with different lengths
HMA_FAST = 9                    # Fast HMA period (was hardcoded 9)
HMA_SLOW = 21                   # Slow HMA period (was hardcoded 21)

# Gate 1 — HMA slope confirmation
SLOPE_LOOKBACK = 3              # Bars over which to measure HMA slope
SLOPE_MIN_PCT = 0.01            # Minimum absolute slope % (0.01 = 0.01% per bar)

# Gate 2 — Crossover freshness
CROSS_FRESHNESS_BARS = 15       # Max bars since last HMA_FAST/HMA_SLOW crossover (~75 min on 5m)

# Gate 3 — Price-HMA alignment (no threshold; structural check only)

# Gate 4 — HMA separation (anti-chop)
MIN_HMA_SEP_ATR_FRAC = 0.15    # Min |HMA_FAST−HMA_SLOW| as fraction of 5m ATR

# Gate 5 — HMA divergence (momentum expanding)
DIVERGENCE_LOOKBACK = 5         # Compare current gap vs gap N bars ago

# ═══════════════════════════════════════════════════════════════════════════════
# V6.8 BROKERAGE / STATUTORY CHARGES CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
BROKERAGE_PCT = 0.03                  # 0.03% per executed order, capped at Rs.20
BROKERAGE_CAP_PER_ORDER = 20.0
STT_SELL_PCT = 0.025                  # Sell side only
TRANSACTION_CHARGE_NSE_PCT = 0.00297
TRANSACTION_CHARGE_BSE_PCT = 0.00375
SEBI_CHARGE_PER_CRORE = 10.0          # Rs.10 / crore turnover
STAMP_BUY_PCT = 0.003                 # Buy side only
GST_PCT = 18.0                        # On (brokerage + sebi + transaction)


@dataclass
class BrokerageBreakdown:
    turnover: float = 0.0
    brokerage: float = 0.0
    stt: float = 0.0
    transaction_charge: float = 0.0
    sebi_charge: float = 0.0
    stamp_charge: float = 0.0
    gst: float = 0.0
    total: float = 0.0

    def add(self, other: "BrokerageBreakdown"):
        self.turnover += float(other.turnover)
        self.brokerage += float(other.brokerage)
        self.stt += float(other.stt)
        self.transaction_charge += float(other.transaction_charge)
        self.sebi_charge += float(other.sebi_charge)
        self.stamp_charge += float(other.stamp_charge)
        self.gst += float(other.gst)
        self.total += float(other.total)

    def to_dict(self) -> Dict[str, float]:
        return {
            "turnover": float(self.turnover),
            "brokerage": float(self.brokerage),
            "stt": float(self.stt),
            "transaction_charge": float(self.transaction_charge),
            "sebi_charge": float(self.sebi_charge),
            "stamp_charge": float(self.stamp_charge),
            "gst": float(self.gst),
            "total": float(self.total),
        }


@dataclass
class BacktestTrade:
    """Represents one lifecycle-managed simulated trade."""

    trade_id: str
    symbol: str
    sector: str
    direction: str  # LONG / SHORT
    entry_time: datetime
    entry_price: float
    initial_qty: int
    qty: int
    initial_stop: float
    current_stop: float
    target_1: float
    atr_at_entry: float
    stage: str = "ACTIVE"  # ACTIVE / PARTIAL / CLOSED
    highest_price: float = 0.0
    lowest_price: float = 0.0
    realized_pnl: float = 0.0
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    exit_reason: str = ""
    # V6.1 additions
    entry_risk_per_share: float = 0.0
    entry_atr_5m: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    be_armed: bool = False
    trail_armed: bool = False
    # V6.2 additions
    notional_at_entry: float = 0.0
    # V6.4 additions — direction matrix tracking
    index_direction: str = ""
    sector_bias_at_entry: str = ""
    signal_direction: str = ""
    # V6.8 additions — brokerage-aware PnL decomposition
    gross_pnl: float = 0.0
    total_turnover: float = 0.0
    total_brokerage: float = 0.0
    total_stt: float = 0.0
    total_transaction_charge: float = 0.0
    total_sebi_charge: float = 0.0
    total_stamp_charge: float = 0.0
    total_gst: float = 0.0
    total_charges: float = 0.0


@dataclass
class DayResult:
    """Daily summary row."""

    day: date
    start_equity: float
    end_equity: float
    pnl: float
    trades: int
    trade_pnls: List[float] = field(default_factory=list)


class SectorBacktesterV6:
    """
    V6.8 backtester — V6.7 quality gates + full brokerage accounting.

    Five new gates filter out low-conviction HMA crossover signals:
      1. HMA slope direction confirmation
      2. Crossover freshness (max bars since cross)
      3. Price-HMA structural alignment (price > HMA9 > HMA21 for LONG)
      4. HMA separation vs ATR (anti-chop)
      5. HMA divergence (momentum expanding, not converging)

    Brokerage charges are applied on every executed order leg and deducted from
    realized PnL in real time.
    """

    def __init__(
        self,
        data_root: Optional[Path] = None,
        starting_equity: Optional[float] = None,
        synthetic_spread_bps: float = 6.0,
        synthetic_circuit_pct: float = 0.10,
        checkpoint_every_days: int = 1,
        exchange: str = "NSE",
    ):
        self.data_root = Path(data_root) if data_root else self._default_data_root()
        self.daily_dir = self.data_root / "daily"
        self.intra_dir = self.data_root / "5minute"
        self.backtest_root = Path(__file__).parent
        self.history_dir = self.backtest_root / "history_v6.8"

        self.synthetic_spread_bps = max(0.0, float(synthetic_spread_bps))
        self.synthetic_circuit_pct = max(0.01, float(synthetic_circuit_pct))
        self.checkpoint_every_days = max(0, int(checkpoint_every_days))
        self.exchange = str(exchange or "NSE").upper()
        if self.exchange not in ("NSE", "BSE"):
            raise ValueError(f"Unsupported exchange '{exchange}'. Allowed: NSE, BSE")
        self.transaction_charge_pct = (
            TRANSACTION_CHARGE_NSE_PCT
            if self.exchange == "NSE"
            else TRANSACTION_CHARGE_BSE_PCT
        )

        # Universe metadata
        self.indices: List[Dict[str, Any]] = []
        self.stocks: List[Dict[str, Any]] = []
        self.sector_map: Dict[str, List[str]] = {}
        self.index_name_by_symbol: Dict[str, str] = {}
        self.index_symbol_by_name: Dict[str, str] = {}
        self.symbol_to_sector_name: Dict[str, str] = {}

        # Market data
        self.daily_data: Dict[str, pd.DataFrame] = {}
        self.intra_data: Dict[str, pd.DataFrame] = {}
        self._daily_before_cache: Dict[Tuple[str, date], pd.DataFrame] = {}
        self._intraday_day_cache: Dict[Tuple[str, date], pd.DataFrame] = {}
        self._intra_row_cache: Dict[Tuple[str, pd.Timestamp], Tuple[Optional[pd.Series], int]] = {}
        self._daily_symbol_metrics_cache: Dict[Tuple[str, date], Optional[Dict[str, Any]]] = {}
        self._intra_np: Dict[str, Dict[str, np.ndarray]] = {}

        # V6 strategy components
        self.regime_detector = MarketRegimeDetector()
        self.sector_scorer = SectorScorer()
        self.risk = RiskManager()
        self.safety = SafetyMonitor()

        # Portfolio state
        self.initial_equity = float(starting_equity or config.DEFAULT_PAPER_EQUITY)
        self.realized_pnl = 0.0
        self.active_trades: Dict[str, BacktestTrade] = {}
        self.trade_history: List[BacktestTrade] = []
        self.trade_counter = 0

        # Runtime state
        self.current_playbook = "INIT"
        self.vix_percentile = 50.0
        self.vix_multiplier = 1.0
        self.vix_ltp = 0.0
        self.nifty_ltp = 0.0
        self.nifty_pct = 0.0
        self.sector_scores: List[SectorScore] = []
        self.active_signals: List[StockSignal] = []
        self.rejected_symbols: Dict[str, datetime] = {}
        self.day_results: List[DayResult] = []

        # V6.2: Capital exposure tracking
        self.capital_blocked_count = 0
        self.peak_deployed_notional = 0.0

        # V6.4: Alignment filter tracking
        self.alignment_blocked_count = 0

        # V6.7: Signal quality gate rejection counters
        self.gate_slope_blocked = 0
        self.gate_freshness_blocked = 0
        self.gate_price_align_blocked = 0
        self.gate_separation_blocked = 0
        self.gate_divergence_blocked = 0

        # Run-history analytics buffers
        self.run_id = ""
        self.run_started_at: Optional[datetime] = None
        self.run_finished_at: Optional[datetime] = None
        self.run_status = "NOT_STARTED"
        self.run_error = ""
        self.signal_counter = 0
        self.signal_records: List[Dict[str, Any]] = []
        self.position_records: List[Dict[str, Any]] = []
        self.all_signal_count = 0
        self.all_position_count = 0
        self.max_positions_slot_available_count = 0
        self.blocked_by_max_positions_count = 0
        self.decision_counts: Counter = Counter()
        self.risk_reason_counts: Counter = Counter()
        self.all_trade_records: List[Dict[str, Any]] = []
        self.all_trade_index_by_trade_id: Dict[str, int] = {}
        self.brokerage_totals = BrokerageBreakdown()
        self.history_output_path: Optional[Path] = None
        self.history_file_date_label = ""
        self.history_file_time_label = ""

        self.initialized = False

    @staticmethod
    def _default_data_root() -> Path:
        return Path(__file__).parent / "data"

    def _log(self, msg: str):
        logger.info(msg)

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.2 — Capital Exposure Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_deployed_notional(self) -> float:
        """Total notional locked in active positions (entry_price * current qty)."""
        return sum(t.entry_price * t.qty for t in self.active_trades.values())

    def _get_available_capital(self) -> float:
        """Cash available for new entries."""
        return self.initial_equity + self.realized_pnl - self._get_deployed_notional()

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.4 — Index Direction & Alignment Helpers
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _get_index_direction(nifty_pct: float) -> str:
        if nifty_pct > 0.05:
            return "UP"
        elif nifty_pct < -0.05:
            return "DOWN"
        return "FLAT"

    @staticmethod
    def _is_aligned(index_dir: str, sec_bias: str, signal_dir: str) -> bool:
        if index_dir == "UP" and sec_bias == "LONG" and signal_dir == "LONG":
            return True
        if index_dir == "DOWN" and sec_bias == "SHORT" and signal_dir == "SHORT":
            return True
        return False

    def _build_direction_matrix(self) -> Dict[str, Any]:
        buckets: Dict[str, List[float]] = {}
        for t in self.trade_history:
            key = f"{t.index_direction},{t.sector_bias_at_entry},{t.signal_direction}"
            buckets.setdefault(key, []).append(float(t.realized_pnl))

        matrix = {}
        for key, pnls in sorted(buckets.items()):
            matrix[key] = {
                "trades": len(pnls),
                "net_pnl": float(sum(pnls)),
                "win_rate": float(sum(1 for p in pnls if p > 0) / len(pnls) * 100) if pnls else 0.0,
            }
        return matrix

    def _calculate_order_charges(self, price: float, qty: int, side: str) -> BrokerageBreakdown:
        qty = max(0, int(qty))
        turnover = max(0.0, float(price) * qty)
        if qty == 0 or turnover <= 0:
            return BrokerageBreakdown()

        side = str(side or "").upper()
        is_buy = side == "BUY"
        is_sell = side == "SELL"

        brokerage = min(turnover * (BROKERAGE_PCT / 100.0), BROKERAGE_CAP_PER_ORDER)
        stt = turnover * (STT_SELL_PCT / 100.0) if is_sell else 0.0
        transaction_charge = turnover * (self.transaction_charge_pct / 100.0)
        sebi_charge = (turnover / 10_000_000.0) * SEBI_CHARGE_PER_CRORE
        stamp_charge = turnover * (STAMP_BUY_PCT / 100.0) if is_buy else 0.0
        gst = (brokerage + sebi_charge + transaction_charge) * (GST_PCT / 100.0)
        total = brokerage + stt + transaction_charge + sebi_charge + stamp_charge + gst

        return BrokerageBreakdown(
            turnover=turnover,
            brokerage=brokerage,
            stt=stt,
            transaction_charge=transaction_charge,
            sebi_charge=sebi_charge,
            stamp_charge=stamp_charge,
            gst=gst,
            total=total,
        )

    def _apply_order_execution(
        self,
        trade: BacktestTrade,
        price: float,
        qty: int,
        side: str,
        gross_pnl_delta: float = 0.0,
    ) -> BrokerageBreakdown:
        charges = self._calculate_order_charges(price, qty, side)
        net_delta = float(gross_pnl_delta) - charges.total

        trade.gross_pnl += float(gross_pnl_delta)
        trade.realized_pnl += net_delta
        trade.total_turnover += charges.turnover
        trade.total_brokerage += charges.brokerage
        trade.total_stt += charges.stt
        trade.total_transaction_charge += charges.transaction_charge
        trade.total_sebi_charge += charges.sebi_charge
        trade.total_stamp_charge += charges.stamp_charge
        trade.total_gst += charges.gst
        trade.total_charges += charges.total

        self.realized_pnl += net_delta
        self.brokerage_totals.add(charges)
        return charges

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.7 — HMA Series Helpers (compute HMA at historical offsets)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _hma_at_offset(closes: np.ndarray, period: int, offset: int = 0) -> float:
        """Compute HMA(period) using closes ending at len-offset.

        offset=0 → current bar, offset=1 → one bar earlier, etc.
        """
        if offset < 0:
            return 0.0
        end = len(closes) - offset
        if end < period + int(np.sqrt(period)):
            return 0.0
        return calculate_hma(closes[:end], period)

    # ═══════════════════════════════════════════════════════════════════════════

    def _start_run_tracking(self, start_date: date, end_date: date):
        self._reset_backtest_state()
        self.run_started_at = datetime.now()
        self.run_finished_at = None
        self.run_id = self.run_started_at.strftime("BT_%Y%m%d_%H%M%S")
        self.run_status = "RUNNING"
        self.run_error = ""
        self.signal_counter = 0
        self.signal_records.clear()
        self.position_records.clear()
        self.all_signal_count = 0
        self.all_position_count = 0
        self.max_positions_slot_available_count = 0
        self.blocked_by_max_positions_count = 0
        self.decision_counts.clear()
        self.risk_reason_counts.clear()
        self.all_trade_records.clear()
        self.all_trade_index_by_trade_id.clear()
        self.history_output_path = None
        self.history_file_date_label = ""
        self.history_file_time_label = ""
        self._log(
            f"Run tracking started | run_id={self.run_id} | range={start_date} -> {end_date}"
        )

    def _reset_backtest_state(self):
        self.realized_pnl = 0.0
        self.active_trades.clear()
        self.trade_history.clear()
        self.day_results.clear()
        self.trade_counter = 0
        self.rejected_symbols.clear()
        self.sector_scores = []
        self.active_signals = []
        self.capital_blocked_count = 0
        self.peak_deployed_notional = 0.0
        self.alignment_blocked_count = 0
        self.gate_slope_blocked = 0
        self.gate_freshness_blocked = 0
        self.gate_price_align_blocked = 0
        self.gate_separation_blocked = 0
        self.gate_divergence_blocked = 0
        self.brokerage_totals = BrokerageBreakdown()
        self._intra_row_cache.clear()
        self._daily_symbol_metrics_cache.clear()

        self.risk = RiskManager()
        self.safety = SafetyMonitor()
        self.risk.state.starting_equity = self.initial_equity
        self.risk.state.daily_start_equity = self.initial_equity
        self.risk.state.daily_high_equity = self.initial_equity
        self.risk.state.equity = self.initial_equity

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dt_time):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): SectorBacktesterV6._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [SectorBacktesterV6._json_safe(v) for v in value]
        if isinstance(value, np.generic):
            return value.item()
        return str(value)

    def _capture_config_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        for key in dir(config):
            if not key.isupper():
                continue
            snapshot[key] = self._json_safe(getattr(config, key))
        # V6.1 constants
        snapshot["V6_1_STOP_ATR_MULT_5M"] = STOP_ATR_MULT_5M
        snapshot["V6_1_STOP_MIN_PCT"] = STOP_MIN_PCT
        snapshot["V6_1_BE_ARM_R"] = BE_ARM_R
        snapshot["V6_1_BE_BUFFER_BPS"] = BE_BUFFER_BPS
        snapshot["V6_1_TRAIL_ARM_R"] = TRAIL_ARM_R
        snapshot["V6_1_TRAIL_LOOKBACK_BARS"] = TRAIL_LOOKBACK_BARS
        snapshot["V6_1_TRAIL_MULT_LOW"] = TRAIL_MULT_LOW
        snapshot["V6_1_TRAIL_MULT_MID"] = TRAIL_MULT_MID
        snapshot["V6_1_TRAIL_MULT_HIGH"] = TRAIL_MULT_HIGH
        # V6.2
        snapshot["V6_2_LEVERAGE_ALLOWED"] = False
        # V6.4
        snapshot["V6_4_ALIGNMENT_FILTER"] = True
        snapshot["V6_4_APPROACH"] = "HARD_BLOCK_MISALIGNED"
        # V6.6 baseline
        snapshot["V6_6_HMA_SOURCE"] = "5M_ONLY"
        snapshot["V6_6_HMA_FAST"] = HMA_FAST
        snapshot["V6_6_HMA_SLOW"] = HMA_SLOW
        snapshot["V6_6_SECTOR_RANK_MAX"] = 3
        snapshot["V6_6_ALLOW_GRADES"] = ["A+"]
        snapshot["V6_6_REMOVED_FACTORS"] = ["RVOL", "STOCH_RSI", "SPREAD_QUALITY"]
        # V6.7: signal quality gates
        snapshot["V6_7_SLOPE_LOOKBACK"] = SLOPE_LOOKBACK
        snapshot["V6_7_SLOPE_MIN_PCT"] = SLOPE_MIN_PCT
        snapshot["V6_7_CROSS_FRESHNESS_BARS"] = CROSS_FRESHNESS_BARS
        snapshot["V6_7_MIN_HMA_SEP_ATR_FRAC"] = MIN_HMA_SEP_ATR_FRAC
        snapshot["V6_7_DIVERGENCE_LOOKBACK"] = DIVERGENCE_LOOKBACK
        # V6.8 brokerage
        snapshot["V6_8_EXCHANGE"] = self.exchange
        snapshot["V6_8_BROKERAGE_PCT"] = BROKERAGE_PCT
        snapshot["V6_8_BROKERAGE_CAP_PER_ORDER"] = BROKERAGE_CAP_PER_ORDER
        snapshot["V6_8_STT_SELL_PCT"] = STT_SELL_PCT
        snapshot["V6_8_TRANSACTION_CHARGE_PCT"] = self.transaction_charge_pct
        snapshot["V6_8_SEBI_CHARGE_PER_CRORE"] = SEBI_CHARGE_PER_CRORE
        snapshot["V6_8_STAMP_BUY_PCT"] = STAMP_BUY_PCT
        snapshot["V6_8_GST_PCT"] = GST_PCT
        return snapshot

    def _next_signal_id(self, ts: pd.Timestamp, symbol: str) -> str:
        self.signal_counter += 1
        return f"SIG_{ts.strftime('%Y%m%d_%H%M')}_{symbol}_{self.signal_counter:06d}"

    def _serialize_trade(self, trade: BacktestTrade) -> Dict[str, Any]:
        return {
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "sector": trade.sector,
            "direction": trade.direction,
            "entry_time": self._json_safe(trade.entry_time),
            "entry_price": float(trade.entry_price),
            "initial_qty": int(trade.initial_qty),
            "exit_time": self._json_safe(trade.exit_time),
            "exit_price": float(trade.exit_price),
            "exit_reason": trade.exit_reason,
            "realized_pnl": float(trade.realized_pnl),
            "gross_pnl": float(trade.gross_pnl),
            "total_turnover": float(trade.total_turnover),
            "total_charges": float(trade.total_charges),
            "brokerage_breakdown": {
                "brokerage": float(trade.total_brokerage),
                "stt": float(trade.total_stt),
                "transaction_charge": float(trade.total_transaction_charge),
                "sebi_charge": float(trade.total_sebi_charge),
                "stamp_charge": float(trade.total_stamp_charge),
                "gst": float(trade.total_gst),
            },
            "stage": trade.stage,
            # V6.1 fields
            "entry_risk_per_share": float(trade.entry_risk_per_share),
            "entry_atr_5m": float(trade.entry_atr_5m),
            "mfe_r": float(trade.mfe_r),
            "mae_r": float(trade.mae_r),
            "be_armed": bool(trade.be_armed),
            "trail_armed": bool(trade.trail_armed),
            # V6.2 fields
            "notional_at_entry": float(trade.notional_at_entry),
            # V6.4 fields
            "index_direction": trade.index_direction,
            "sector_bias_at_entry": trade.sector_bias_at_entry,
            "signal_direction": trade.signal_direction,
        }

    def _build_run_summary(self) -> Dict[str, Any]:
        final_equity = self.initial_equity + self.realized_pnl
        total_return = final_equity - self.initial_equity
        total_return_pct = ((final_equity / self.initial_equity) - 1.0) * 100.0 if self.initial_equity > 0 else 0.0

        constrained_signal_count = len(self.signal_records)
        constrained_position_count = len(self.position_records)
        executed_positions = sum(1 for row in self.position_records if row.get("executed_trade"))
        all_signal_count = self.all_signal_count
        all_position_count = self.all_position_count
        all_trade_count = len(self.all_trade_records)
        blocked_by_max_positions = self.blocked_by_max_positions_count
        max_slot_available_count = self.max_positions_slot_available_count
        risk_reason_counter = Counter(self.risk_reason_counts)
        decision_counter = Counter(self.decision_counts)
        gross_return = total_return + self.brokerage_totals.total
        brokerage_pct_of_turnover = (
            self.brokerage_totals.total / self.brokerage_totals.turnover * 100.0
            if self.brokerage_totals.turnover > 0
            else 0.0
        )

        return {
            "initial_equity": float(self.initial_equity),
            "final_equity": float(final_equity),
            "total_return": float(total_return),
            "total_return_pct": float(total_return_pct),
            "gross_return_before_charges": float(gross_return),
            "trading_days": int(len(self.day_results)),
            "closed_trades": int(len(self.trade_history)),
            "a_grade_signals": int(constrained_signal_count),
            "position_candidates": int(constrained_position_count),
            "executed_positions": int(executed_positions),
            "all_a_grade_signals": int(all_signal_count),
            "all_position_candidates": int(all_position_count),
            "all_trade_candidates": int(all_trade_count),
            "max_positions_slot_available_count": int(max_slot_available_count),
            "blocked_by_max_positions_count": int(blocked_by_max_positions),
            "decision_counts": dict(decision_counter),
            "risk_reason_counts": dict(risk_reason_counter),
            # V6.8 brokerage
            "exchange": self.exchange,
            "transaction_charge_pct": float(self.transaction_charge_pct),
            "total_turnover": float(self.brokerage_totals.turnover),
            "total_charges": float(self.brokerage_totals.total),
            "brokerage_pct_of_turnover": float(brokerage_pct_of_turnover),
            "brokerage_breakdown": {
                "brokerage": float(self.brokerage_totals.brokerage),
                "stt": float(self.brokerage_totals.stt),
                "transaction_charge": float(self.brokerage_totals.transaction_charge),
                "sebi_charge": float(self.brokerage_totals.sebi_charge),
                "stamp_charge": float(self.brokerage_totals.stamp_charge),
                "gst": float(self.brokerage_totals.gst),
            },
            # V6.2
            "capital_blocked_count": int(self.capital_blocked_count),
            "peak_deployed_notional": float(self.peak_deployed_notional),
            "peak_utilization_pct": float(
                (self.peak_deployed_notional / self.initial_equity * 100.0)
                if self.initial_equity > 0 else 0.0
            ),
            # V6.4
            "alignment_blocked_count": int(self.alignment_blocked_count),
            # V6.7: quality gate rejection stats
            "gate_slope_blocked": int(self.gate_slope_blocked),
            "gate_freshness_blocked": int(self.gate_freshness_blocked),
            "gate_price_align_blocked": int(self.gate_price_align_blocked),
            "gate_separation_blocked": int(self.gate_separation_blocked),
            "gate_divergence_blocked": int(self.gate_divergence_blocked),
        }

    def _ensure_history_output_path(self, start_date: date, end_date: date) -> Path:
        if self.history_output_path is not None:
            return self.history_output_path

        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp_dt = datetime.now()
        date_part = stamp_dt.strftime("%d-%m-%Y")
        time_display = stamp_dt.strftime("%I:%M %p").lower()

        time_part_file = time_display.replace(":", "-").replace(" ", "_")
        base_name = f"backtest_history_{date_part}_{time_part_file}"
        out_path = self.history_dir / f"{base_name}.json"
        seq = 2
        while out_path.exists():
            out_path = self.history_dir / f"{base_name}_{seq}.json"
            seq += 1

        self.history_output_path = out_path
        self.history_file_date_label = date_part
        self.history_file_time_label = time_display
        return out_path

    def _write_run_history_file(
        self,
        start_date: date,
        end_date: date,
        trading_days: List[date],
        is_checkpoint: bool = False,
    ):
        out_path = self._ensure_history_output_path(start_date, end_date)
        payload_finished_at = self.run_finished_at
        if is_checkpoint and payload_finished_at is None:
            payload_finished_at = datetime.now()

        payload: Dict[str, Any] = {
            "run": {
                "run_id": self.run_id,
                "status": self.run_status,
                "error": self.run_error,
                "is_checkpoint": bool(is_checkpoint),
                "started_at": self._json_safe(self.run_started_at),
                "finished_at": self._json_safe(payload_finished_at),
                "duration_seconds": (
                    (payload_finished_at - self.run_started_at).total_seconds()
                    if self.run_started_at and payload_finished_at
                    else None
                ),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "trading_days": [d.isoformat() for d in trading_days],
                "history_file_date_label": self.history_file_date_label,
                "history_file_time_label": self.history_file_time_label,
                "data_root": str(self.data_root),
                "history_file": str(out_path),
            },
            "inputs": {
                "synthetic_spread_bps": float(self.synthetic_spread_bps),
                "synthetic_circuit_pct": float(self.synthetic_circuit_pct),
                "checkpoint_every_days": int(self.checkpoint_every_days),
                "exchange": self.exchange,
                "transaction_charge_pct": float(self.transaction_charge_pct),
                "max_concurrent_positions": int(config.MAX_CONCURRENT_POSITIONS),
                "max_positions_per_sector": int(config.MAX_POSITIONS_PER_SECTOR),
                "max_positions_per_stock": int(config.MAX_POSITIONS_PER_STOCK),
            },
            "config_snapshot": self._capture_config_snapshot(),
            "summary": self._build_run_summary(),
            "daily_results": [
                {
                    "day": row.day.isoformat(),
                    "start_equity": float(row.start_equity),
                    "end_equity": float(row.end_equity),
                    "pnl": float(row.pnl),
                    "trades": int(row.trades),
                    "trade_pnls": [float(x) for x in row.trade_pnls],
                }
                for row in self.day_results
            ],
            "all_trade_records": self.all_trade_records,
            "signal_records": self.signal_records,
            "position_records": self.position_records,
            "trade_records": [self._serialize_trade(t) for t in self.trade_history],
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        if is_checkpoint:
            self._log(f"History checkpoint saved: {out_path}")
        else:
            self._log(f"History output saved: {out_path}")

    def initialize(self) -> bool:
        """Load universe and parquet data into memory."""
        self._load_universe()

        if not self.daily_dir.exists() or not self.intra_dir.exists():
            self._log(f"Missing data folders under: {self.data_root}")
            self._log("Run backtest_v6/data_miner_v6.py first, or point --data-root to existing parquet data.")
            return False

        all_symbols = {"NIFTY 50", "INDIA VIX"}
        all_symbols.update([idx["symbol"] for idx in self.indices])
        all_symbols.update([stk["symbol"] for stk in self.stocks])

        loaded_daily = 0
        loaded_intra = 0
        self._intra_np.clear()

        for symbol in sorted(all_symbols):
            d_path = self.daily_dir / f"{symbol}.parquet"
            if d_path.exists():
                d_df = self._load_parquet(d_path)
                if not d_df.empty:
                    self.daily_data[symbol] = d_df
                    loaded_daily += 1

            i_path = self.intra_dir / f"{symbol}.parquet"
            if i_path.exists():
                i_df = self._load_parquet(i_path)
                if not i_df.empty:
                    self._prepare_intraday_frame(i_df)
                    self.intra_data[symbol] = i_df
                    self._intra_np[symbol] = {
                        "high": i_df["high"].to_numpy(dtype=float),
                        "low": i_df["low"].to_numpy(dtype=float),
                        "close": i_df["close"].to_numpy(dtype=float),
                        "volume": i_df["volume"].to_numpy(dtype=float),
                    }
                    loaded_intra += 1

        self._log(
            f"Loaded data from {self.data_root} | daily files: {loaded_daily}, 5m files: {loaded_intra}"
        )

        self.risk.state.starting_equity = self.initial_equity
        self.risk.state.daily_start_equity = self.initial_equity
        self.risk.state.daily_high_equity = self.initial_equity
        self.risk.state.equity = self.initial_equity
        self.initialized = True
        return True

    def _load_universe(self):
        if not config.UNIVERSE_PATH.exists():
            raise FileNotFoundError(f"Universe file not found: {config.UNIVERSE_PATH}")

        with open(config.UNIVERSE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)

        self.indices = payload.get("indices", [])
        self.stocks = [s for s in payload.get("stocks", []) if s.get("token")]

        self.sector_map.clear()
        self.index_name_by_symbol.clear()
        self.index_symbol_by_name.clear()
        self.symbol_to_sector_name.clear()

        for idx in self.indices:
            name = idx.get("name", "")
            symbol = idx.get("symbol", "")
            if name and symbol:
                self.index_name_by_symbol[symbol] = name
                self.index_symbol_by_name[name] = symbol

        for stk in self.stocks:
            sym = stk.get("symbol")
            sectors = stk.get("indices", []) or []
            if sym and sectors and sym not in self.symbol_to_sector_name:
                self.symbol_to_sector_name[sym] = sectors[0]

            for sec_name in sectors:
                self.sector_map.setdefault(sec_name, []).append(sym)

        self._log(f"Universe loaded | indices: {len(self.indices)} | stocks: {len(self.stocks)}")

    @staticmethod
    def _load_parquet(path: Path) -> pd.DataFrame:
        df = pd.read_parquet(path)
        if "date" not in df.columns:
            return pd.DataFrame()

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        if hasattr(df["date"].dt, "tz") and df["date"].dt.tz is not None:
            df["date"] = df["date"].dt.tz_convert(None)

        df = df.sort_values("date")
        df = df.drop_duplicates(subset=["date"], keep="last")
        df = df.set_index("date", drop=False)
        return df

    @staticmethod
    def _prepare_intraday_frame(df: pd.DataFrame):
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        df["_tp_vol"] = typical * df["volume"]
        df["_date_only"] = df["date"].dt.date
        df["_cum_vol"] = df.groupby("_date_only")["volume"].cumsum()
        df["_cum_tp_vol"] = df.groupby("_date_only")["_tp_vol"].cumsum()
        df["vwap"] = np.where(df["_cum_vol"] > 0, df["_cum_tp_vol"] / df["_cum_vol"], df["close"])
        df["date_only"] = df["_date_only"]
        df.drop(columns=["_tp_vol", "_date_only", "_cum_vol", "_cum_tp_vol"], inplace=True)

    def _validate_data_sufficiency(self, start_date: date, end_date: date) -> bool:
        nifty_daily = self.daily_data.get("NIFTY 50")
        nifty_intra = self.intra_data.get("NIFTY 50")
        vix_daily = self.daily_data.get("INDIA VIX")

        if nifty_daily is None or nifty_daily.empty:
            self._log("NIFTY 50 daily data missing.")
            return False
        if nifty_intra is None or nifty_intra.empty:
            self._log("NIFTY 50 5minute data missing.")
            return False
        if vix_daily is None or vix_daily.empty:
            self._log("INDIA VIX daily data missing.")
            return False

        required_start = pd.Timestamp(start_date) - pd.Timedelta(days=config.LOOKBACK_DAYS_VIX)
        if nifty_daily.index.min() > required_start:
            self._log(
                f"Insufficient NIFTY daily lookback. Need <= {required_start.date()}, have {nifty_daily.index.min().date()}."
            )
            return False
        if vix_daily.index.min() > required_start:
            self._log(
                f"Insufficient VIX daily lookback. Need <= {required_start.date()}, have {vix_daily.index.min().date()}."
            )
            return False

        mask = (nifty_intra.index.date >= start_date) & (nifty_intra.index.date <= end_date)
        if not np.any(mask):
            self._log(f"No NIFTY intraday candles between {start_date} and {end_date}.")
            return False

        return True

    def _get_trading_days(self, start_date: date, end_date: date) -> List[date]:
        nifty = self.intra_data["NIFTY 50"]
        mask = (nifty.index.date >= start_date) & (nifty.index.date <= end_date)
        days = sorted(set(nifty.index[mask].date))
        return days

    def _get_daily_before(self, symbol: str, day: date) -> pd.DataFrame:
        key = (symbol, day)
        cached = self._daily_before_cache.get(key)
        if cached is not None:
            return cached

        df = self.daily_data.get(symbol)
        if df is None or df.empty:
            out = pd.DataFrame()
        else:
            pos = df.index.searchsorted(pd.Timestamp(day))
            out = df.iloc[:pos]
        self._daily_before_cache[key] = out
        return out

    def _get_daily_symbol_metrics(self, symbol: str, day: date) -> Optional[Dict[str, Any]]:
        key = (symbol, day)
        cached = self._daily_symbol_metrics_cache.get(key)
        if cached is not None or key in self._daily_symbol_metrics_cache:
            return cached

        daily_hist = self._get_daily_before(symbol, day)
        if daily_hist is None or len(daily_hist) < 20:
            self._daily_symbol_metrics_cache[key] = None
            return None

        closes = daily_hist["close"].to_numpy(dtype=float)
        highs = daily_hist["high"].to_numpy(dtype=float)
        lows = daily_hist["low"].to_numpy(dtype=float)
        vols = daily_hist["volume"].to_numpy(dtype=float)
        adv = ExecutionFilters.calculate_adv_crores(closes, vols)

        atr_period = 10
        if len(closes) < atr_period + 1:
            atr_10 = 0.0
        else:
            atr_10 = calculate_atr(
                highs[-(atr_period + 1):],
                lows[-(atr_period + 1):],
                closes[-(atr_period + 1):],
                period=atr_period,
            )

        out = {
            "daily_hist": daily_hist,
            "closes": closes,
            "adv": float(adv),
            "atr_10": float(atr_10),
        }
        self._daily_symbol_metrics_cache[key] = out
        return out

    def _get_intraday_day(self, symbol: str, day: date) -> pd.DataFrame:
        key = (symbol, day)
        cached = self._intraday_day_cache.get(key)
        if cached is not None:
            return cached

        df = self.intra_data.get(symbol)
        if df is None or df.empty:
            out = pd.DataFrame()
        else:
            start_ts = pd.Timestamp(day)
            end_ts = start_ts + pd.Timedelta(days=1)
            out = df.loc[(df.index >= start_ts) & (df.index < end_ts)]
        self._intraday_day_cache[key] = out
        return out

    def _get_intra_row(self, symbol: str, ts: pd.Timestamp) -> Tuple[Optional[pd.Series], int]:
        key = (symbol, ts)
        cached = self._intra_row_cache.get(key)
        if cached is not None:
            return cached

        df = self.intra_data.get(symbol)
        if df is None or df.empty:
            out = (None, -1)
            self._intra_row_cache[key] = out
            return out

        pos = df.index.searchsorted(ts)
        if pos >= len(df):
            out = (None, int(pos))
            self._intra_row_cache[key] = out
            return out
        if df.index[pos] != ts:
            out = (None, int(pos))
            self._intra_row_cache[key] = out
            return out
        out = (df.iloc[pos], int(pos))
        self._intra_row_cache[key] = out
        return out

    def get_playbook(self, now: dt_time) -> str:
        if now < config.MARKET_OPEN_TIME:
            return "PRE_MARKET"
        if now < config.ENTRY_START_TIME:
            return "WAIT"
        if now < config.ENTRY_CUTOFF_TIME:
            return "MAIN"
        if now < config.FORCE_EXIT_TIME:
            return "EXIT_ONLY"
        if now < config.MARKET_CLOSE_TIME:
            return "FORCE_EXIT"
        return "AFTER_CLOSE"

    def _build_day_baselines(self, day: date) -> Dict[str, Dict[str, float]]:
        baselines: Dict[str, Dict[str, float]] = {}
        all_symbols = {"NIFTY 50", "INDIA VIX"}
        all_symbols.update([idx["symbol"] for idx in self.indices])
        all_symbols.update([stk["symbol"] for stk in self.stocks])

        for symbol in all_symbols:
            d_hist = self._get_daily_before(symbol, day)
            if d_hist is None or d_hist.empty:
                continue

            base: Dict[str, float] = {
                "prev_close": float(d_hist.iloc[-1]["close"]),
            }
            if len(d_hist) >= 20:
                base["close_20d"] = float(d_hist.iloc[-20]["close"])
                base["close_3d"] = float(d_hist.iloc[-3]["close"])
            baselines[symbol] = base

        return baselines

    def _get_vix_window(self, day: date) -> List[float]:
        vix_hist = self._get_daily_before("INDIA VIX", day)
        if vix_hist is None or vix_hist.empty:
            return []
        return [float(x) for x in vix_hist["close"].tail(20).tolist()]

    def _update_sector_scores(self, ts: pd.Timestamp, baselines: Dict[str, Dict[str, float]], regime: str):
        n_base = baselines.get("NIFTY 50", {})
        n_c20 = n_base.get("close_20d", 0.0)
        n_c3 = n_base.get("close_3d", 0.0)
        n_prev = n_base.get("prev_close", 0.0)
        if n_c20 <= 0 or n_c3 <= 0 or n_prev <= 0:
            self.sector_scores = []
            return

        nifty_row, _ = self._get_intra_row("NIFTY 50", ts)
        if nifty_row is None:
            self.sector_scores = []
            return

        self.nifty_ltp = float(nifty_row["close"])
        n_ret_20 = (self.nifty_ltp - n_c20) / n_c20
        n_ret_3 = (self.nifty_ltp - n_c3) / n_c3
        n_ret_d = (self.nifty_ltp - n_prev) / n_prev
        self.nifty_pct = n_ret_d * 100.0

        scores: List[SectorScore] = []
        for idx in self.indices:
            sec_name = idx.get("name", "")
            sec_symbol = idx.get("symbol", "")
            if sec_name in ("NIFTY 50", "INDIA VIX"):
                continue

            sec_row, _ = self._get_intra_row(sec_symbol, ts)
            if sec_row is None:
                continue

            sec_base = baselines.get(sec_symbol, {})
            s_c20 = sec_base.get("close_20d", 0.0)
            s_c3 = sec_base.get("close_3d", 0.0)
            s_prev = sec_base.get("prev_close", 0.0)
            if s_c20 <= 0 or s_c3 <= 0 or s_prev <= 0:
                continue

            sec_ltp = float(sec_row["close"])
            s_ret_20 = (sec_ltp - s_c20) / s_c20
            s_ret_3 = (sec_ltp - s_c3) / s_c3
            s_ret_d = (sec_ltp - s_prev) / s_prev

            constituents = self.sector_map.get(sec_name, [])
            valid = above = below = 0
            for sym in constituents:
                stk_row, _ = self._get_intra_row(sym, ts)
                if stk_row is None:
                    continue
                vwap = float(stk_row.get("vwap", 0.0))
                if vwap <= 0:
                    continue
                valid += 1
                close_price = float(stk_row["close"])
                if close_price > vwap:
                    above += 1
                elif close_price < vwap:
                    below += 1

            breadth = (above / valid) - (below / valid) if valid > 0 else 0.0
            scores.append(
                SectorScore(
                    symbol=sec_symbol,
                    price=sec_ltp,
                    change_pct=s_ret_d * 100.0,
                    structural_rs=(s_ret_20 - n_ret_20) * 100.0,
                    shortterm_rs=(s_ret_3 - n_ret_3) * 100.0,
                    intraday_rs=(s_ret_d - n_ret_d) * 100.0,
                    breadth=breadth,
                )
            )

        ranked = self.sector_scorer.score_all(scores, regime, self.nifty_pct)
        self._mark_top3_sectors(ranked)
        self.sector_scores = ranked

    @staticmethod
    def _mark_top3_sectors(ranked_sectors: List[SectorScore]):
        for sec in ranked_sectors:
            sec.is_selected = False
        for sec in ranked_sectors:
            if sec.rank <= 3 and sec.bias in ("LONG", "SHORT"):
                sec.is_selected = True

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.7 — Enhanced HMA Analysis (replaces simple _get_hma_alignment)
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_hma_alignment_v67(
        self,
        symbol: str,
        current_price: float,
        intra_pos: int,
        atr_5m: float,
    ) -> Dict[str, Any]:
        """Return a rich HMA analysis dict with alignment, slopes, crossover
        age, separation, and divergence — used by the V6.7 signal builder.

        Returns dict with keys:
            align        : BULLISH / BEARISH / MIXED
            hma9, hma21  : current HMA values
            slope9, slope21 : percentage slope per bar
            cross_bars_ago : bars since last HMA9/HMA21 crossover (-1 if unknown)
            separation   : abs(hma9 - hma21)
            sep_atr_frac : separation / atr_5m
            is_diverging : True if gap widening vs DIVERGENCE_LOOKBACK bars ago
            reject_reasons : list of gate rejection reasons (empty = all passed)
        """
        result: Dict[str, Any] = {
            "align": "MIXED",
            "hma9": 0.0,
            "hma21": 0.0,
            "slope9": 0.0,
            "slope21": 0.0,
            "cross_bars_ago": -1,
            "separation": 0.0,
            "sep_atr_frac": 0.0,
            "is_diverging": False,
            "reject_reasons": [],
        }

        intra_np = self._intra_np.get(symbol)
        if intra_np is None or intra_pos <= 0:
            return result

        closes_5m = intra_np["close"][:intra_pos]
        min_bars = HMA_SLOW + int(np.sqrt(HMA_SLOW))
        if len(closes_5m) < min_bars:
            return result

        # Build full series including current price for HMA calculation
        series = np.append(closes_5m, current_price)
        n = len(series)

        # ── Current HMA values ──
        hma9 = calculate_hma(series, HMA_FAST)
        hma21 = calculate_hma(series, HMA_SLOW)
        if hma9 <= 0 or hma21 <= 0:
            return result

        result["hma9"] = float(hma9)
        result["hma21"] = float(hma21)

        if hma9 > hma21:
            result["align"] = "BULLISH"
        elif hma9 < hma21:
            result["align"] = "BEARISH"
        else:
            return result  # exactly equal — MIXED, no gates to check

        direction = "LONG" if result["align"] == "BULLISH" else "SHORT"
        reject_reasons: List[str] = []

        # ── Gate 1: HMA Slope Confirmation ──
        # Compute HMA at SLOPE_LOOKBACK bars ago and compare
        hma9_prev = self._hma_at_offset(series, HMA_FAST, SLOPE_LOOKBACK)
        hma21_prev = self._hma_at_offset(series, HMA_SLOW, SLOPE_LOOKBACK)

        if hma9_prev > 0 and hma21_prev > 0:
            slope9 = (hma9 - hma9_prev) / hma9_prev * 100.0  # pct change over SLOPE_LOOKBACK bars
            slope21 = (hma21 - hma21_prev) / hma21_prev * 100.0
            result["slope9"] = float(slope9)
            result["slope21"] = float(slope21)

            slope9_per_bar = slope9 / SLOPE_LOOKBACK
            slope21_per_bar = slope21 / SLOPE_LOOKBACK

            if direction == "LONG":
                if slope9_per_bar < SLOPE_MIN_PCT or slope21_per_bar < SLOPE_MIN_PCT:
                    reject_reasons.append(
                        f"SLOPE_FAIL: HMA9_slope={slope9_per_bar:.4f}%/bar HMA21_slope={slope21_per_bar:.4f}%/bar (need>{SLOPE_MIN_PCT}%)"
                    )
            else:
                if slope9_per_bar > -SLOPE_MIN_PCT or slope21_per_bar > -SLOPE_MIN_PCT:
                    reject_reasons.append(
                        f"SLOPE_FAIL: HMA9_slope={slope9_per_bar:.4f}%/bar HMA21_slope={slope21_per_bar:.4f}%/bar (need<-{SLOPE_MIN_PCT}%)"
                    )

        # ── Gate 2: Crossover Freshness ──
        # Walk backwards through series to find the bar where HMA9 crossed HMA21
        max_scan = min(60, n - 25)  # don't scan too far back
        cross_bars_ago = -1
        for offset in range(1, max_scan):
            h9 = self._hma_at_offset(series, HMA_FAST, offset)
            h21 = self._hma_at_offset(series, HMA_SLOW, offset)
            if h9 <= 0 or h21 <= 0:
                break
            # Detect sign flip: current hma9>hma21 but at offset hma9<=hma21 (or vice versa)
            if direction == "LONG" and h9 <= h21:
                cross_bars_ago = offset
                break
            if direction == "SHORT" and h9 >= h21:
                cross_bars_ago = offset
                break

        result["cross_bars_ago"] = cross_bars_ago
        if cross_bars_ago < 0:
            # Could not find crossover within scan range — treat as stale
            reject_reasons.append(
                f"CROSS_STALE: no crossover found within {max_scan} bars"
            )
        elif cross_bars_ago > CROSS_FRESHNESS_BARS:
            reject_reasons.append(
                f"CROSS_STALE: crossover {cross_bars_ago} bars ago (max={CROSS_FRESHNESS_BARS})"
            )

        # ── Gate 3: Price-HMA Alignment ──
        if direction == "LONG":
            if not (current_price > hma9 > hma21):
                reject_reasons.append(
                    f"PRICE_ALIGN_FAIL: need Price({current_price:.2f})>HMA9({hma9:.2f})>HMA21({hma21:.2f})"
                )
        else:
            if not (current_price < hma9 < hma21):
                reject_reasons.append(
                    f"PRICE_ALIGN_FAIL: need Price({current_price:.2f})<HMA9({hma9:.2f})<HMA21({hma21:.2f})"
                )

        # ── Gate 4: HMA Separation (anti-chop) ──
        separation = abs(hma9 - hma21)
        result["separation"] = float(separation)
        if atr_5m > 0:
            sep_frac = separation / atr_5m
            result["sep_atr_frac"] = float(sep_frac)
            if sep_frac < MIN_HMA_SEP_ATR_FRAC:
                reject_reasons.append(
                    f"SEP_CHOP: gap/ATR={sep_frac:.4f} (need>={MIN_HMA_SEP_ATR_FRAC})"
                )

        # ── Gate 5: HMA Divergence (expanding gap) ──
        h9_old = self._hma_at_offset(series, HMA_FAST, DIVERGENCE_LOOKBACK)
        h21_old = self._hma_at_offset(series, HMA_SLOW, DIVERGENCE_LOOKBACK)
        if h9_old > 0 and h21_old > 0:
            old_gap = abs(h9_old - h21_old)
            is_diverging = separation > old_gap
            result["is_diverging"] = is_diverging
            if not is_diverging:
                reject_reasons.append(
                    f"CONVERGING: current_gap={separation:.4f} <= old_gap({DIVERGENCE_LOOKBACK}bars)={old_gap:.4f}"
                )

        result["reject_reasons"] = reject_reasons
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.7 — Signal Builder (replaces _build_signal_v66)
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_signal_v67(
        self,
        symbol: str,
        sector: str,
        price: float,
        change_pct: float,
        hma_info: Dict[str, Any],
        sector_rank: int,
        sector_bias: str,
    ) -> StockSignal:
        """Build signal with V6.6 A+ criteria + V6.7 quality gates."""

        hma_align = hma_info["align"]
        hma9_5m = hma_info["hma9"]
        hma21_5m = hma_info["hma21"]

        if hma_align == "BULLISH":
            direction = "LONG"
        elif hma_align == "BEARISH":
            direction = "SHORT"
        else:
            direction = "NONE"

        reasons: List[str] = []
        grade = "C"
        score = 0.0
        multiplier = config.GRADE_MULTIPLIERS.get("C", 0.0)

        # ── V6.6 structural checks (unchanged) ──
        if sector_rank > 3:
            reasons.append(f"SECTOR_RANK_BLOCKED: rank={sector_rank} > 3")
        elif direction == "NONE":
            reasons.append("HMA9_21_NOT_ALIGNED")
        elif sector_bias == "NEUTRAL":
            reasons.append("SECTOR_BIAS_NEUTRAL")
        elif sector_bias == "LONG" and direction != "LONG":
            reasons.append("SECTOR_BIAS_LONG_MISMATCH")
        elif sector_bias == "SHORT" and direction != "SHORT":
            reasons.append("SECTOR_BIAS_SHORT_MISMATCH")
        else:
            index_dir = self._get_index_direction(self.nifty_pct)
            if not self._is_aligned(index_dir, sector_bias, direction):
                reasons.append(
                    f"ALIGNMENT_BLOCKED: Index={index_dir} Sector={sector_bias} Signal={direction}"
                )
                self.alignment_blocked_count += 1
            else:
                # ── V6.7 quality gates ──
                gate_rejects = hma_info.get("reject_reasons", [])
                if gate_rejects:
                    # Classify which gates failed for counter tracking
                    for r in gate_rejects:
                        if r.startswith("SLOPE_FAIL"):
                            self.gate_slope_blocked += 1
                        elif r.startswith("CROSS_STALE"):
                            self.gate_freshness_blocked += 1
                        elif r.startswith("PRICE_ALIGN_FAIL"):
                            self.gate_price_align_blocked += 1
                        elif r.startswith("SEP_CHOP"):
                            self.gate_separation_blocked += 1
                        elif r.startswith("CONVERGING"):
                            self.gate_divergence_blocked += 1
                    reasons.extend(gate_rejects)
                else:
                    # All V6.6 + V6.7 gates passed → A+
                    grade = "A+"
                    score = float(config.THRESHOLD_A_PLUS)
                    multiplier = config.GRADE_MULTIPLIERS.get("A+", 1.0)

                    slope_info = f"slope9={hma_info['slope9']:.3f}% slope21={hma_info['slope21']:.3f}%"
                    cross_info = f"cross_age={hma_info['cross_bars_ago']}bars"
                    sep_info = f"sep/ATR={hma_info['sep_atr_frac']:.3f}"
                    div_info = "DIVERGING" if hma_info["is_diverging"] else "FLAT"

                    reasons.extend(
                        [
                            (
                                f"HMA9>HMA21_5M={hma9_5m:.2f}/{hma21_5m:.2f}"
                                if direction == "LONG"
                                else f"HMA9<HMA21_5M={hma9_5m:.2f}/{hma21_5m:.2f}"
                            ),
                            f"TOP3_SECTOR_RANK={sector_rank}",
                            f"ALIGNMENT_OK: Index={index_dir} Sector={sector_bias} Signal={direction}",
                            f"QUALITY_GATES_PASSED: {slope_info} | {cross_info} | {sep_info} | {div_info}",
                        ]
                    )

        return StockSignal(
            symbol=symbol,
            sector=sector,
            price=float(price),
            change_pct=float(change_pct),
            hma_align=hma_align,
            sector_rank=int(sector_rank),
            grade=grade,
            multiplier=float(multiplier),
            direction=direction,
            score=float(score),
            reasons=reasons,
        )

    def _synthetic_microstructure(
        self, symbol: str, ltp: float, baselines: Dict[str, Dict[str, float]]
    ) -> Tuple[float, float, float, float]:
        spread = max(0.01, ltp * (self.synthetic_spread_bps / 10_000.0))
        bid = max(0.01, ltp - spread / 2.0)
        ask = ltp + spread / 2.0

        prev_close = baselines.get(symbol, {}).get("prev_close", ltp)
        if prev_close <= 0:
            prev_close = ltp
        upper_circuit = prev_close * (1.0 + self.synthetic_circuit_pct)
        lower_circuit = max(0.01, prev_close * (1.0 - self.synthetic_circuit_pct))
        return bid, ask, upper_circuit, lower_circuit

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.1 — 5-minute ATR helper
    # ═══════════════════════════════════════════════════════════════════════════

    def _compute_5m_atr(self, symbol: str, intra_pos: int, period: int = 14) -> float:
        intra_np = self._intra_np.get(symbol)
        if intra_np is None or intra_pos < period:
            return 0.0
        end = intra_pos + 1
        if end < period + 1:
            return 0.0
        start = end - (period + 1)
        highs = intra_np["high"][start:end]
        lows = intra_np["low"][start:end]
        closes = intra_np["close"][start:end]
        return calculate_atr(highs, lows, closes, period=period)

    def _scan_tradeable_stocks(
        self,
        ts: pd.Timestamp,
        baselines: Dict[str, Dict[str, float]],
        regime: str,
    ):
        selected_sector_symbols = [s.symbol for s in self.sector_scores if s.is_selected]
        if not selected_sector_symbols:
            self.active_signals = []
            return

        sector_info = {s.symbol: s for s in self.sector_scores}
        candidates: List[str] = []

        for sec_sym in selected_sector_symbols:
            sec_name = self.index_name_by_symbol.get(sec_sym)
            if sec_name:
                candidates.extend(self.sector_map.get(sec_name, []))

        active_symbols = sorted({trade.symbol for trade in self.active_trades.values()})
        candidates.extend(active_symbols)
        candidates = list(dict.fromkeys(candidates))

        self.active_signals = []
        can_enter = self.current_playbook == "MAIN"

        for scan_order, symbol in enumerate(candidates, start=1):
            row, intra_pos = self._get_intra_row(symbol, ts)
            if row is None:
                continue

            metrics = self._get_daily_symbol_metrics(symbol, ts.date())
            if metrics is None:
                continue

            adv = float(metrics["adv"])
            if adv < config.MIN_ADV_CRORES:
                continue

            curr_price = float(row["close"])
            atr = float(metrics["atr_10"])
            if atr <= 0:
                continue

            atr_5m = self._compute_5m_atr(symbol, intra_pos, period=14)

            bid, ask, u_circuit, l_circuit = self._synthetic_microstructure(symbol, curr_price, baselines)
            passed, gate_reason = ExecutionFilters.check_gate(
                bid=bid,
                ask=ask,
                price=curr_price,
                atr=atr,
                u_circuit=u_circuit,
                l_circuit=l_circuit,
            )

            # V6.7: Rich HMA analysis (replaces simple alignment call)
            hma_info = self._get_hma_alignment_v67(symbol, curr_price, intra_pos, atr_5m)

            stock_sector_name = self.symbol_to_sector_name.get(symbol, "UNKNOWN")
            stock_sector_symbol = self.index_symbol_by_name.get(stock_sector_name, "")
            sec_score = sector_info.get(stock_sector_symbol)
            sec_rank = sec_score.rank if sec_score else 16
            sec_bias = sec_score.bias if sec_score else "NEUTRAL"

            stock_prev = baselines.get(symbol, {}).get("prev_close", 0.0)
            change_pct = ((curr_price - stock_prev) / stock_prev * 100.0) if stock_prev > 0 else 0.0

            signal = self._build_signal_v67(
                symbol=symbol,
                sector=stock_sector_name,
                price=curr_price,
                change_pct=change_pct,
                hma_info=hma_info,
                sector_rank=sec_rank,
                sector_bias=sec_bias,
            )
            signal.hma9_5m = float(hma_info["hma9"])
            signal.hma21_5m = float(hma_info["hma21"])
            signal.gate_passed = passed
            signal.gate_reason = gate_reason
            self.active_signals.append(signal)

            if signal.grade == "A+":
                self._process_entry(
                    signal=signal,
                    ltp=curr_price,
                    atr=atr,
                    atr_5m=atr_5m,
                    ts=ts,
                    can_enter=can_enter,
                    gate_passed=passed,
                    gate_reason=gate_reason,
                    adv_crores=adv,
                    regime=regime,
                    scan_order=scan_order,
                    sec_bias=sec_bias,
                    hma_info=hma_info,
                )

    def _process_entry(
        self,
        signal: StockSignal,
        ltp: float,
        atr: float,
        atr_5m: float,
        ts: pd.Timestamp,
        can_enter: bool,
        gate_passed: bool,
        gate_reason: str,
        adv_crores: float,
        regime: str,
        scan_order: int,
        sec_bias: str = "NEUTRAL",
        hma_info: Optional[Dict[str, Any]] = None,
    ):
        signal_id = self._next_signal_id(ts, signal.symbol)
        open_positions_before = int(self.risk.state.open_positions_count)
        max_positions_limit = int(config.MAX_CONCURRENT_POSITIONS)
        max_positions_slot_available = open_positions_before < max_positions_limit

        last_rejected = self.rejected_symbols.get(signal.symbol)
        in_cooldown = bool(last_rejected and (ts - last_rejected).total_seconds() < 300)
        if last_rejected and (ts - last_rejected).total_seconds() >= 300:
            self.rejected_symbols.pop(signal.symbol, None)

        risk_allowed = False
        risk_reason = ""
        if can_enter and not in_cooldown and signal.direction in ("LONG", "SHORT"):
            risk_allowed, risk_reason = self.risk.can_open_new_trade(signal.symbol, signal.sector)

        R0 = max(atr_5m * STOP_ATR_MULT_5M, ltp * STOP_MIN_PCT) if atr_5m > 0 else ltp * STOP_MIN_PCT
        stop_dist = R0

        stop_price = None
        target_1 = None
        sizing = None
        if signal.direction in ("LONG", "SHORT") and stop_dist > 0:
            stop_price = ltp - stop_dist if signal.direction == "LONG" else ltp + stop_dist
            sizing = self.risk.calculate_position_size(
                entry_price=ltp,
                stop_price=stop_price,
                grade=signal.grade,
                vix_multiplier=self.vix_multiplier,
                current_time=ts.time(),
            )
            if sizing.risk_per_share > 0:
                target_1 = (
                    ltp + (sizing.risk_per_share * config.TARGET_1_MULT)
                    if signal.direction == "LONG"
                    else ltp - (sizing.risk_per_share * config.TARGET_1_MULT)
                )

        available_capital = self._get_available_capital()
        capital_capped_shares = 0
        if sizing is not None and sizing.is_allowed and sizing.shares > 0 and ltp > 0:
            max_shares_by_capital = int(available_capital / ltp) if available_capital > 0 else 0
            capital_capped_shares = min(sizing.shares, max(0, max_shares_by_capital))

        entry_decision = "NOT_EVALUATED"
        executed_trade = False
        executed_trade_id = ""

        index_direction = self._get_index_direction(self.nifty_pct)

        if not can_enter:
            entry_decision = "PLAYBOOK_BLOCKED"
        elif not gate_passed:
            entry_decision = f"GATE_FAIL:{gate_reason}"
        elif in_cooldown:
            entry_decision = "REJECTION_COOLDOWN"
        elif signal.direction not in ("LONG", "SHORT"):
            entry_decision = f"INVALID_DIRECTION:{signal.direction}"
        elif stop_dist <= 0 or stop_price is None:
            entry_decision = "INVALID_STOP_DISTANCE"
        elif sizing is None:
            entry_decision = "SIZING_NOT_COMPUTED"
        elif not sizing.is_allowed:
            entry_decision = f"SIZING_REJECTED:{sizing.reason}"
            self.rejected_symbols[signal.symbol] = ts
        elif capital_capped_shares < 1:
            entry_decision = "INSUFFICIENT_CAPITAL"
            self.capital_blocked_count += 1
        elif not risk_allowed:
            entry_decision = f"RISK_REJECTED:{risk_reason}"
        else:
            self.trade_counter += 1
            trade_id = f"TRD_{signal.symbol}_{ts.strftime('%Y%m%d_%H%M')}_{self.trade_counter}"
            notional = float(ltp) * capital_capped_shares
            trade = BacktestTrade(
                trade_id=trade_id,
                symbol=signal.symbol,
                sector=signal.sector or "UNKNOWN",
                direction=signal.direction,
                entry_time=ts.to_pydatetime(),
                entry_price=float(ltp),
                initial_qty=int(capital_capped_shares),
                qty=int(capital_capped_shares),
                initial_stop=float(stop_price),
                current_stop=float(stop_price),
                target_1=float(target_1 or ltp),
                atr_at_entry=float(atr),
                highest_price=float(ltp),
                lowest_price=float(ltp),
                entry_risk_per_share=float(R0),
                entry_atr_5m=float(atr_5m),
                notional_at_entry=float(notional),
                index_direction=index_direction,
                sector_bias_at_entry=sec_bias,
                signal_direction=signal.direction,
            )
            entry_side = "BUY" if signal.direction == "LONG" else "SELL"
            self._apply_order_execution(
                trade=trade,
                price=float(ltp),
                qty=int(capital_capped_shares),
                side=entry_side,
                gross_pnl_delta=0.0,
            )
            self.active_trades[trade_id] = trade

            if signal.symbol not in self.risk.state.active_symbols:
                self.risk.state.active_symbols.append(signal.symbol)
            self.risk.state.open_positions_count += 1
            self.risk.state.symbol_exposure[signal.symbol] = (
                self.risk.state.symbol_exposure.get(signal.symbol, 0) + 1
            )
            self.risk.state.sector_exposure[signal.sector] = (
                self.risk.state.sector_exposure.get(signal.sector, 0) + 1
            )

            entry_decision = "EXECUTED"
            executed_trade = True
            executed_trade_id = trade_id

        blocked_by_max_positions = (
            (not risk_allowed) and bool(risk_reason) and risk_reason.startswith("MAX_POSITIONS")
        )
        blocked_by_sector_limit = (
            (not risk_allowed) and bool(risk_reason) and risk_reason.startswith("MAX_SECTOR_LIMIT")
        )
        blocked_by_stock_limit = (
            (not risk_allowed) and bool(risk_reason) and risk_reason.startswith("MAX_STOCK_LIMIT")
        )

        # V6.7: Include quality gate metadata in signal/position records
        hma_quality = {}
        if hma_info is not None:
            hma_quality = {
                "slope9": float(hma_info.get("slope9", 0.0)),
                "slope21": float(hma_info.get("slope21", 0.0)),
                "cross_bars_ago": int(hma_info.get("cross_bars_ago", -1)),
                "separation": float(hma_info.get("separation", 0.0)),
                "sep_atr_frac": float(hma_info.get("sep_atr_frac", 0.0)),
                "is_diverging": bool(hma_info.get("is_diverging", False)),
            }

        signal_row = {
            "signal_id": signal_id,
            "timestamp": ts.isoformat(),
            "scan_order": int(scan_order),
            "playbook": self.current_playbook,
            "regime": regime,
            "symbol": signal.symbol,
            "sector": signal.sector,
            "direction": signal.direction,
            "grade": signal.grade,
            "score": float(signal.score),
            "reasons": list(signal.reasons),
            "price": float(ltp),
            "change_pct": float(signal.change_pct),
            "hma_align": signal.hma_align,
            "hma9_5m": float(getattr(signal, "hma9_5m", 0.0)),
            "hma21_5m": float(getattr(signal, "hma21_5m", 0.0)),
            "sector_rank": int(signal.sector_rank),
            "gate_passed": bool(gate_passed),
            "gate_reason": gate_reason,
            "adv_crores": float(adv_crores),
            "atr": float(atr),
            "atr_5m": float(atr_5m),
            "vix_ltp": float(self.vix_ltp),
            "vix_percentile": float(self.vix_percentile),
            "vix_multiplier": float(self.vix_multiplier),
            "nifty_ltp": float(self.nifty_ltp),
            "nifty_pct": float(self.nifty_pct),
            "open_positions_before": int(open_positions_before),
            "max_positions_limit": int(max_positions_limit),
            "max_positions_slot_available": bool(max_positions_slot_available),
            "blocked_by_max_positions": bool(blocked_by_max_positions),
            "risk_allowed": bool(risk_allowed),
            "risk_reason": risk_reason,
            "entry_decision": entry_decision,
            "executed_trade": bool(executed_trade),
            "executed_trade_id": executed_trade_id,
            "executed_within_max_positions": bool(executed_trade and max_positions_slot_available),
            "available_capital": float(available_capital),
            "capital_capped_shares": int(capital_capped_shares),
            "index_direction": index_direction,
            "sector_bias": sec_bias,
            "signal_direction": signal.direction,
            # V6.7: quality gate metadata
            "hma_quality": hma_quality,
        }

        position_row = {
            "signal_id": signal_id,
            "timestamp": ts.isoformat(),
            "symbol": signal.symbol,
            "sector": signal.sector,
            "direction": signal.direction,
            "grade": signal.grade,
            "entry_price": float(ltp),
            "atr": float(atr),
            "atr_5m": float(atr_5m),
            "stop_price": float(stop_price) if stop_price is not None else None,
            "target_1": float(target_1) if target_1 is not None else None,
            "open_positions_before": int(open_positions_before),
            "max_positions_limit": int(max_positions_limit),
            "max_positions_slot_available": bool(max_positions_slot_available),
            "max_positions_considered": True,
            "blocked_by_max_positions": bool(blocked_by_max_positions),
            "blocked_by_sector_limit": bool(blocked_by_sector_limit),
            "blocked_by_stock_limit": bool(blocked_by_stock_limit),
            "risk_allowed": bool(risk_allowed),
            "risk_reason": risk_reason,
            "sizing_allowed": bool(sizing.is_allowed) if sizing is not None else False,
            "sizing_reason": sizing.reason if sizing is not None else "SIZING_NOT_COMPUTED",
            "sizing_shares": int(sizing.shares) if sizing is not None else 0,
            "risk_amount": float(sizing.risk_amount) if sizing is not None else 0.0,
            "risk_per_share": float(sizing.risk_per_share) if sizing is not None else 0.0,
            "effective_risk_pct": float(sizing.effective_risk_pct) if sizing is not None else 0.0,
            "entry_decision": entry_decision,
            "executed_trade": bool(executed_trade),
            "executed_trade_id": executed_trade_id,
            "executed_within_max_positions": bool(executed_trade and max_positions_slot_available),
            "available_capital": float(available_capital),
            "capital_capped_shares": int(capital_capped_shares),
            "notional": float(ltp * capital_capped_shares) if capital_capped_shares > 0 else 0.0,
            "index_direction": index_direction,
            "sector_bias": sec_bias,
            "signal_direction": signal.direction,
            # V6.7: quality gate metadata
            "hma_quality": hma_quality,
        }

        all_trade_id = executed_trade_id if executed_trade else f"POT_{signal_id}"
        if executed_trade:
            all_trade_row = self._serialize_trade(trade)
        else:
            all_trade_row = {
                "trade_id": all_trade_id,
                "symbol": signal.symbol,
                "sector": signal.sector,
                "direction": signal.direction,
                "entry_time": ts.isoformat(),
                "entry_price": float(ltp),
                "initial_qty": int(sizing.shares) if sizing is not None else 0,
                "exit_time": None,
                "exit_price": 0.0,
                "exit_reason": entry_decision,
                "realized_pnl": 0.0,
                "gross_pnl": 0.0,
                "total_turnover": 0.0,
                "total_charges": 0.0,
                "brokerage_breakdown": {
                    "brokerage": 0.0,
                    "stt": 0.0,
                    "transaction_charge": 0.0,
                    "sebi_charge": 0.0,
                    "stamp_charge": 0.0,
                    "gst": 0.0,
                },
                "stage": "NOT_EXECUTED",
                "index_direction": index_direction,
                "sector_bias": sec_bias,
                "signal_direction": signal.direction,
            }

        self.all_signal_count += 1
        self.all_position_count += 1
        if max_positions_slot_available:
            self.max_positions_slot_available_count += 1
        if blocked_by_max_positions:
            self.blocked_by_max_positions_count += 1
        if entry_decision:
            self.decision_counts[entry_decision] += 1
        if risk_reason:
            self.risk_reason_counts[risk_reason] += 1

        all_trade_idx = len(self.all_trade_records)
        self.all_trade_records.append(all_trade_row)
        if executed_trade and executed_trade_id:
            self.all_trade_index_by_trade_id[executed_trade_id] = all_trade_idx

        if executed_trade:
            self.signal_records.append(signal_row)
            self.position_records.append(position_row)

    @staticmethod
    def _calculate_trade_pnl(direction: str, entry: float, exit_price: float, qty: int) -> float:
        if qty <= 0:
            return 0.0
        if direction == "LONG":
            return (exit_price - entry) * qty
        return (entry - exit_price) * qty

    def _close_trade(self, trade_id: str, trade: BacktestTrade, ts: pd.Timestamp, exit_price: float, reason: str):
        if trade.qty > 0:
            close_qty = int(trade.qty)
            gross_pnl = self._calculate_trade_pnl(trade.direction, trade.entry_price, exit_price, close_qty)
            exit_side = "SELL" if trade.direction == "LONG" else "BUY"
            self._apply_order_execution(
                trade=trade,
                price=float(exit_price),
                qty=close_qty,
                side=exit_side,
                gross_pnl_delta=float(gross_pnl),
            )
            trade.qty = 0

        trade.exit_time = ts.to_pydatetime()
        trade.exit_price = float(exit_price)
        trade.exit_reason = reason
        trade.stage = "CLOSED"

        all_idx = self.all_trade_index_by_trade_id.get(trade_id)
        if all_idx is not None and 0 <= all_idx < len(self.all_trade_records):
            self.all_trade_records[all_idx] = self._serialize_trade(trade)
            self.all_trade_index_by_trade_id.pop(trade_id, None)

        self.trade_history.append(copy.deepcopy(trade))
        self.active_trades.pop(trade_id, None)

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.1 — Chandelier rewrite
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_chandelier(self, trade: BacktestTrade, intra_pos: int) -> float:
        intra_np = self._intra_np.get(trade.symbol)
        if intra_np is None or intra_pos < 0:
            return trade.current_stop

        end = intra_pos + 1
        if end < TRAIL_LOOKBACK_BARS + 1:
            return trade.current_stop

        atr_start = end - (TRAIL_LOOKBACK_BARS + 1)
        highs_arr = intra_np["high"][atr_start:end]
        lows_arr = intra_np["low"][atr_start:end]
        closes_arr = intra_np["close"][atr_start:end]
        atr_5m = calculate_atr(highs_arr, lows_arr, closes_arr, period=TRAIL_LOOKBACK_BARS)
        if atr_5m <= 0:
            return trade.current_stop

        if trade.mfe_r >= 2.0:
            trail_mult = TRAIL_MULT_HIGH
        elif trade.mfe_r >= 1.0:
            trail_mult = TRAIL_MULT_MID
        else:
            trail_mult = TRAIL_MULT_LOW

        atr_buffer = atr_5m * trail_mult

        lookback_start = end - TRAIL_LOOKBACK_BARS
        if trade.direction == "LONG":
            anchor = float(np.max(intra_np["high"][lookback_start:end]))
            return anchor - atr_buffer
        else:
            anchor = float(np.min(intra_np["low"][lookback_start:end]))
            return anchor + atr_buffer

    # ═══════════════════════════════════════════════════════════════════════════
    # V6.1 — Active trade management loop
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_active_trades(self, ts: pd.Timestamp):
        for trade_id, trade in list(self.active_trades.items()):
            row, intra_pos = self._get_intra_row(trade.symbol, ts)
            if row is None:
                continue

            high = float(row["high"])
            low = float(row["low"])

            trade.highest_price = max(trade.highest_price, high)
            trade.lowest_price = min(trade.lowest_price, low)

            if trade.entry_risk_per_share > 0:
                if trade.direction == "LONG":
                    fav = (trade.highest_price - trade.entry_price) / trade.entry_risk_per_share
                    adv = (trade.entry_price - trade.lowest_price) / trade.entry_risk_per_share
                else:
                    fav = (trade.entry_price - trade.lowest_price) / trade.entry_risk_per_share
                    adv = (trade.highest_price - trade.entry_price) / trade.entry_risk_per_share
                trade.mfe_r = max(trade.mfe_r, max(fav, 0.0))
                trade.mae_r = max(trade.mae_r, max(adv, 0.0))

            stop_hit = (
                trade.direction == "LONG" and low <= trade.current_stop
            ) or (
                trade.direction == "SHORT" and high >= trade.current_stop
            )
            if stop_hit:
                reason = "STOP_TRAIL" if (trade.be_armed or trade.trail_armed) else "STOP_HARD"
                self._close_trade(trade_id, trade, ts, float(trade.current_stop), reason)
                continue

            if (
                not trade.be_armed
                and trade.entry_risk_per_share > 0
                and trade.mfe_r >= BE_ARM_R
            ):
                if trade.direction == "LONG":
                    be_stop = trade.entry_price + (BE_BUFFER_BPS * trade.entry_price / 10000)
                    if be_stop > trade.current_stop:
                        trade.current_stop = be_stop
                else:
                    be_stop = trade.entry_price - (BE_BUFFER_BPS * trade.entry_price / 10000)
                    if be_stop < trade.current_stop:
                        trade.current_stop = be_stop
                trade.be_armed = True

            if not trade.trail_armed and trade.mfe_r >= TRAIL_ARM_R:
                trade.trail_armed = True

            if trade.trail_armed:
                new_trail = self._calculate_chandelier(trade, intra_pos)
                if trade.direction == "LONG" and new_trail > trade.current_stop:
                    trade.current_stop = new_trail
                elif trade.direction == "SHORT" and new_trail < trade.current_stop:
                    trade.current_stop = new_trail

            if trade.stage == "ACTIVE":
                target_hit = (
                    trade.direction == "LONG" and high >= trade.target_1
                ) or (
                    trade.direction == "SHORT" and low <= trade.target_1
                )
                if target_hit:
                    partial_qty = max(1, int(trade.qty * config.TARGET_1_EXIT_PCT))
                    partial_qty = min(partial_qty, trade.qty)
                    partial_gross_pnl = self._calculate_trade_pnl(
                        trade.direction,
                        trade.entry_price,
                        float(trade.target_1),
                        partial_qty,
                    )
                    partial_side = "SELL" if trade.direction == "LONG" else "BUY"
                    self._apply_order_execution(
                        trade=trade,
                        price=float(trade.target_1),
                        qty=int(partial_qty),
                        side=partial_side,
                        gross_pnl_delta=float(partial_gross_pnl),
                    )
                    trade.qty -= partial_qty

                    if trade.qty <= 0:
                        self._close_trade(trade_id, trade, ts, float(trade.target_1), "TARGET1_FULL")
                        continue

                    if trade.direction == "LONG":
                        trade.current_stop = max(trade.current_stop, trade.entry_price)
                    else:
                        trade.current_stop = min(trade.current_stop, trade.entry_price)
                    trade.stage = "PARTIAL"

                    all_idx = self.all_trade_index_by_trade_id.get(trade_id)
                    if all_idx is not None and 0 <= all_idx < len(self.all_trade_records):
                        self.all_trade_records[all_idx] = self._serialize_trade(trade)

    def _force_exit_all(self, ts: pd.Timestamp, reason: str = "FORCE_EXIT"):
        for trade_id, trade in list(self.active_trades.items()):
            row, _ = self._get_intra_row(trade.symbol, ts)
            exit_price = float(row["close"]) if row is not None else float(trade.entry_price)
            self._close_trade(trade_id, trade, ts, exit_price, reason)

    def _mark_to_market(self, ts: pd.Timestamp) -> Tuple[float, float, float]:
        positions = []
        unrealized = 0.0
        symbol_exposure: Dict[str, int] = {}
        sector_exposure: Dict[str, int] = {}

        for trade in self.active_trades.values():
            row, _ = self._get_intra_row(trade.symbol, ts)
            ltp = float(row["close"]) if row is not None else trade.entry_price
            upnl = self._calculate_trade_pnl(trade.direction, trade.entry_price, ltp, trade.qty)
            unrealized += upnl

            signed_qty = trade.qty if trade.direction == "LONG" else -trade.qty
            positions.append(
                {
                    "symbol": trade.symbol,
                    "qty": signed_qty,
                    "entry_price": trade.entry_price,
                    "sector": trade.sector,
                }
            )

            symbol_exposure[trade.symbol] = symbol_exposure.get(trade.symbol, 0) + 1
            sector_exposure[trade.sector] = sector_exposure.get(trade.sector, 0) + 1

        current_pnl = self.realized_pnl + unrealized
        current_equity = self.initial_equity + current_pnl

        self.risk.update_account(
            equity=current_equity,
            pnl=current_pnl,
            positions=positions,
            symbol_exposure=symbol_exposure,
            sector_exposure=sector_exposure,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
        )
        self.risk.state.active_symbols = sorted(symbol_exposure.keys())

        deployed = self._get_deployed_notional()
        if deployed > self.peak_deployed_notional:
            self.peak_deployed_notional = deployed

        return current_equity, current_pnl, unrealized

    def _run_day(self, day: date) -> DayResult:
        self._daily_before_cache.clear()
        self._intraday_day_cache.clear()
        self._daily_symbol_metrics_cache.clear()
        self._intra_row_cache.clear()

        day_nifty = self._get_intraday_day("NIFTY 50", day)
        day_start_equity = self.initial_equity + self.realized_pnl

        if day_nifty.empty:
            return DayResult(day=day, start_equity=day_start_equity, end_equity=day_start_equity, pnl=0.0, trades=0)

        baselines = self._build_day_baselines(day)
        vix_window = self._get_vix_window(day)

        self.safety = SafetyMonitor()
        self.rejected_symbols.clear()
        self.sector_scores = []
        self.active_signals = []
        self.risk.state.daily_start_equity = day_start_equity
        self.risk.state.daily_high_equity = day_start_equity
        self.risk.kill_switch_active = False
        self.risk.kill_switch_reason = ""

        trade_count_before = len(self.trade_history)

        for ts, nifty_row in day_nifty.iterrows():
            self._intra_row_cache.clear()
            self.current_playbook = self.get_playbook(ts.time())

            self.nifty_ltp = float(nifty_row["close"])
            n_prev = baselines.get("NIFTY 50", {}).get("prev_close", 0.0)
            self.nifty_pct = ((self.nifty_ltp - n_prev) / n_prev * 100.0) if n_prev > 0 else 0.0

            vix_row, _ = self._get_intra_row("INDIA VIX", ts)
            if vix_row is not None:
                self.vix_ltp = float(vix_row["close"])
            else:
                self.vix_ltp = float(baselines.get("INDIA VIX", {}).get("prev_close", 0.0))

            self.vix_percentile = self.regime_detector.calculate_percentile(self.vix_ltp, vix_window)
            self.vix_multiplier = self.regime_detector.get_vix_multiplier(self.vix_percentile)

            regime = self.regime_detector.get_regime(self.vix_percentile)
            self._update_sector_scores(ts, baselines, regime)

            self._update_active_trades(ts)

            if self.current_playbook == "FORCE_EXIT":
                self._force_exit_all(ts, reason="FORCE_EXIT")

            self._mark_to_market(ts)
            kill_halt, _ = self.risk.check_kill_switches(self.vix_percentile)

            self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
            if self.safety.is_halted and self.active_trades:
                self._force_exit_all(ts, reason="SAFETY_HALT")
                self._mark_to_market(ts)

            if self.current_playbook == "MAIN" and not kill_halt and not self.safety.is_halted:
                self._scan_tradeable_stocks(ts, baselines, regime=regime)
            else:
                self.active_signals = []

        last_ts = day_nifty.index[-1]
        if self.active_trades:
            self._force_exit_all(last_ts, reason="FORCE_EXIT")
        day_end_equity, _, _ = self._mark_to_market(last_ts)

        day_trades = self.trade_history[trade_count_before:]
        day_pnl = day_end_equity - day_start_equity
        return DayResult(
            day=day,
            start_equity=day_start_equity,
            end_equity=day_end_equity,
            pnl=day_pnl,
            trades=len(day_trades),
            trade_pnls=[float(t.realized_pnl) for t in day_trades],
        )

    def run_backtest(self, start_date: date, end_date: date):
        self._start_run_tracking(start_date, end_date)
        trading_days: List[date] = []

        try:
            if not self.initialized:
                if not self.initialize():
                    self.run_status = "INIT_FAILED"
                    return

            if not self._validate_data_sufficiency(start_date, end_date):
                self.run_status = "VALIDATION_FAILED"
                return

            trading_days = self._get_trading_days(start_date, end_date)
            if not trading_days:
                self.run_status = "NO_TRADING_DAYS"
                self._log("No trading sessions found in requested range.")
                return

            print("\n" + "=" * 150)
            print(
                f"{'DATE':<12} | {'START EQUITY':>14} | {'END EQUITY':>14} | {'DAY PNL':>12} | {'TRADES':>6} | TRADE PNLS"
            )
            print("=" * 150)

            self.day_results.clear()
            for idx, day in enumerate(trading_days, start=1):
                result = self._run_day(day)
                self.day_results.append(result)

                trade_str = ", ".join([f"{p:+.0f}" for p in result.trade_pnls]) if result.trade_pnls else "-"
                print(
                    f"{day} | {result.start_equity:>14,.0f} | {result.end_equity:>14,.0f} | "
                    f"{result.pnl:>+12,.0f} | {result.trades:>6} | {trade_str}"
                )

                if self.checkpoint_every_days > 0 and (idx % self.checkpoint_every_days == 0):
                    self._write_run_history_file(
                        start_date,
                        end_date,
                        trading_days[:idx],
                        is_checkpoint=True,
                    )

            self.run_status = "COMPLETED"
            self._print_grand_summary()
        except Exception as exc:
            self.run_status = "ERROR"
            self.run_error = str(exc)
            raise
        finally:
            self.run_finished_at = datetime.now()
            self._write_run_history_file(start_date, end_date, trading_days)

    def _print_grand_summary(self):
        final_equity = self.initial_equity + self.realized_pnl
        total_return = final_equity - self.initial_equity
        total_return_pct = ((final_equity / self.initial_equity) - 1.0) * 100.0
        gross_return = total_return + self.brokerage_totals.total

        print("\n" + "=" * 80)
        print("V6.8 BACKTEST SUMMARY (QUALITY GATES + BROKERAGE)")
        print("-" * 80)
        print(f"Data Root:           {self.data_root}")
        print(f"Exchange:            {self.exchange} (Txn: {self.transaction_charge_pct:.5f}%)")
        print(f"Initial Equity:      {self.initial_equity:,.0f}")
        print(f"Final Equity:        {final_equity:,.0f}")
        print(f"Gross Return:        {gross_return:+,.0f} (before charges)")
        print(f"Total Charges:       {-self.brokerage_totals.total:+,.0f}")
        print(f"Total Return:        {total_return:+,.0f} ({total_return_pct:.2f}%)")
        print(f"Trading Days:        {len(self.day_results)}")
        print(f"Total Trades:        {len(self.trade_history)}")

        if self.trade_history:
            pnls = [float(t.realized_pnl) for t in self.trade_history]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            win_rate = len(wins) / len(pnls) if pnls else 0.0
            avg_pnl = float(np.mean(pnls)) if pnls else 0.0
            std_pnl = float(np.std(pnls)) if pnls else 0.0
            sharpe = (avg_pnl / std_pnl) if std_pnl > 0 else 0.0
            profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")

            print(f"Win Rate:            {win_rate:.1%}")
            print(f"Wins / Losses:       {len(wins)} / {len(losses)}")
            print(f"Expectancy:          {avg_pnl:+,.0f} per trade")
            print(f"Sharpe (trade pnl):  {sharpe:.2f}")
            print(f"Max Win:             {max(pnls):+,.0f}")
            print(f"Max Loss:            {min(pnls):+,.0f}")
            print(f"Profit Factor:       {profit_factor:.2f}")

            # Exit reason breakdown
            reason_counts = Counter(t.exit_reason for t in self.trade_history)
            print(f"\nExit Reasons:")
            for reason, count in reason_counts.most_common():
                pct = count / len(self.trade_history) * 100
                print(f"  {reason:<20s} {count:>5d}  ({pct:.1f}%)")

            # MFE/MAE summary
            mfe_vals = [t.mfe_r for t in self.trade_history]
            mae_vals = [t.mae_r for t in self.trade_history]
            be_count = sum(1 for t in self.trade_history if t.be_armed)
            trail_count = sum(1 for t in self.trade_history if t.trail_armed)
            print(f"\nRisk Management:")
            print(f"  Median MFE (R):    {float(np.median(mfe_vals)):.2f}")
            print(f"  Median MAE (R):    {float(np.median(mae_vals)):.2f}")
            print(f"  BE Armed:          {be_count} ({be_count/len(self.trade_history)*100:.1f}%)")
            print(f"  Trail Armed:       {trail_count} ({trail_count/len(self.trade_history)*100:.1f}%)")

            equity_curve = [self.initial_equity]
            for trade in sorted(self.trade_history, key=lambda t: t.exit_time or t.entry_time):
                equity_curve.append(equity_curve[-1] + float(trade.realized_pnl))
            peak = equity_curve[0]
            max_dd = 0.0
            for eq in equity_curve:
                peak = max(peak, eq)
                if peak > 0:
                    dd = (peak - eq) / peak * 100.0
                    max_dd = max(max_dd, dd)
            print(f"Max Drawdown:        {max_dd:.2f}%")

            # Capital exposure summary
            peak_util = (self.peak_deployed_notional / self.initial_equity * 100.0) if self.initial_equity > 0 else 0.0
            notionals = [t.notional_at_entry for t in self.trade_history if t.notional_at_entry > 0]
            avg_notional = float(np.mean(notionals)) if notionals else 0.0
            print(f"\nCapital Exposure (V6.2 — No Leverage):")
            print(f"  Peak Deployed:     {self.peak_deployed_notional:,.0f} ({peak_util:.1f}% of equity)")
            print(f"  Avg Trade Notional:{avg_notional:,.0f}")
            print(f"  Capital Blocked:   {self.capital_blocked_count} signals rejected (INSUFFICIENT_CAPITAL)")

            charge_pct = (
                self.brokerage_totals.total / self.brokerage_totals.turnover * 100.0
                if self.brokerage_totals.turnover > 0
                else 0.0
            )
            print(f"\nBrokerage & Statutory Charges (V6.8):")
            print(f"  Total Turnover:    {self.brokerage_totals.turnover:,.0f}")
            print(f"  Brokerage:         {self.brokerage_totals.brokerage:,.0f}")
            print(f"  STT/CTT:           {self.brokerage_totals.stt:,.0f}")
            print(f"  Transaction:       {self.brokerage_totals.transaction_charge:,.0f}")
            print(f"  SEBI:              {self.brokerage_totals.sebi_charge:,.0f}")
            print(f"  Stamp Duty:        {self.brokerage_totals.stamp_charge:,.0f}")
            print(f"  GST:               {self.brokerage_totals.gst:,.0f}")
            print(f"  Total Charges:     {self.brokerage_totals.total:,.0f} ({charge_pct:.3f}% of turnover)")

            # Alignment Filter
            print(f"\nAlignment Filter (V6.4 — Hard Block):")
            print(f"  Alignment Blocked: {self.alignment_blocked_count} A+ signals demoted to C")
            matrix = self._build_direction_matrix()
            if matrix:
                print(f"\n  {'DIRECTION BUCKET':<30s} {'TRADES':>7s} {'NET PNL':>12s} {'WIN RATE':>9s}")
                print(f"  {'-'*60}")
                aligned_trades = 0
                aligned_pnl = 0.0
                mismatched_trades = 0
                mismatched_pnl = 0.0
                for key, stats in sorted(matrix.items()):
                    parts = key.split(",")
                    is_aligned = (
                        (parts[0] == "UP" and parts[1] == "LONG" and parts[2] == "LONG") or
                        (parts[0] == "DOWN" and parts[1] == "SHORT" and parts[2] == "SHORT")
                    )
                    marker = "  [OK]" if is_aligned else "  [X]"
                    print(
                        f"{marker} {key:<28s} {stats['trades']:>7d} {stats['net_pnl']:>+12,.0f} {stats['win_rate']:>8.1f}%"
                    )
                    if is_aligned:
                        aligned_trades += stats["trades"]
                        aligned_pnl += stats["net_pnl"]
                    else:
                        mismatched_trades += stats["trades"]
                        mismatched_pnl += stats["net_pnl"]
                print(f"  {'-'*60}")
                total_t = aligned_trades + mismatched_trades
                aligned_pct = (aligned_trades / total_t * 100) if total_t > 0 else 0
                print(f"  Aligned:    {aligned_trades:>5d} trades  {aligned_pnl:>+12,.0f} PnL  ({aligned_pct:.1f}%)")
                print(f"  Mismatched: {mismatched_trades:>5d} trades  {mismatched_pnl:>+12,.0f} PnL  ({100-aligned_pct:.1f}%)")

            # V6.7: Signal Quality Gate Breakdown
            total_gate_blocks = (
                self.gate_slope_blocked
                + self.gate_freshness_blocked
                + self.gate_price_align_blocked
                + self.gate_separation_blocked
                + self.gate_divergence_blocked
            )
            print(f"\nV6.7 Signal Quality Gates:")
            print(f"  Total gate rejections:    {total_gate_blocks}")
            print(f"  ├─ Slope fail:            {self.gate_slope_blocked}")
            print(f"  ├─ Crossover stale:       {self.gate_freshness_blocked}")
            print(f"  ├─ Price-HMA misalign:    {self.gate_price_align_blocked}")
            print(f"  ├─ Separation (chop):     {self.gate_separation_blocked}")
            print(f"  └─ Converging (no div):   {self.gate_divergence_blocked}")

        print("=" * 80 + "\n")

    def export_trades(self, filepath: Optional[Path] = None):
        out_path = Path(filepath) if filepath else (self.data_root / "backtest_trades_v6.8.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.trade_history:
            self._log("No trades to export.")
            return

        rows = []
        for t in self.trade_history:
            rows.append(
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "sector": t.sector,
                    "direction": t.direction,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "initial_qty": t.initial_qty,
                    "gross_pnl": t.gross_pnl,
                    "realized_pnl": t.realized_pnl,
                    "total_turnover": t.total_turnover,
                    "total_charges": t.total_charges,
                    "total_brokerage": t.total_brokerage,
                    "total_stt": t.total_stt,
                    "total_transaction_charge": t.total_transaction_charge,
                    "total_sebi_charge": t.total_sebi_charge,
                    "total_stamp_charge": t.total_stamp_charge,
                    "total_gst": t.total_gst,
                    "stage": t.stage,
                    "exit_reason": t.exit_reason,
                    "entry_risk_per_share": t.entry_risk_per_share,
                    "entry_atr_5m": t.entry_atr_5m,
                    "mfe_r": t.mfe_r,
                    "mae_r": t.mae_r,
                    "be_armed": t.be_armed,
                    "trail_armed": t.trail_armed,
                    "notional_at_entry": t.notional_at_entry,
                    "index_direction": t.index_direction,
                    "sector_bias_at_entry": t.sector_bias_at_entry,
                    "signal_direction": t.signal_direction,
                }
            )

        pd.DataFrame(rows).to_csv(out_path, index=False)
        self._log(f"Exported {len(rows)} trades to {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V6.8 sector backtest engine (quality gates + brokerage)")
    parser.add_argument("--start", type=str, default="2026-01-05", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2026-01-10", help="End date YYYY-MM-DD")
    parser.add_argument("--data-root", type=str, default=None, help="Data folder containing daily/ and 5minute/")
    parser.add_argument("--spread-bps", type=float, default=6.0, help="Synthetic bid/ask spread in basis points")
    parser.add_argument("--circuit-pct", type=float, default=0.10, help="Synthetic circuit band (fraction)")
    parser.add_argument(
        "--exchange",
        type=str,
        default="NSE",
        choices=["NSE", "BSE"],
        help="Exchange used for transaction-charge model",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=1,
        help="Checkpoint cadence in trading days (0 disables mid-run checkpoints)",
    )
    parser.add_argument("--export", action="store_true", help="Export closed trades to CSV")
    parser.add_argument("--export-path", type=str, default=None, help="Custom CSV path for --export")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    root = Path(args.data_root) if args.data_root else None

    engine = SectorBacktesterV6(
        data_root=root,
        synthetic_spread_bps=args.spread_bps,
        synthetic_circuit_pct=args.circuit_pct,
        checkpoint_every_days=args.checkpoint_every,
        exchange=args.exchange,
    )
    engine.run_backtest(start, end)
    if args.export:
        export_path = Path(args.export_path) if args.export_path else None
        engine.export_trades(export_path)
