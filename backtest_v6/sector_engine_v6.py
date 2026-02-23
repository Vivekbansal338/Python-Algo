
"""
===============================================================================
V6 SECTOR BACKTEST ENGINE
===============================================================================
Backtest engine aligned with the current V6 runtime stack:
- v6/config.py (timings + constants)
- v6/brain.py (regime, scoring, grading, risk, safety)
- v6/data_engine.py (indicator functions)

Notes:
- Uses OHLCV parquet data (daily + 5minute).
- Simulates microstructure gate with configurable synthetic spread/circuit values
  because historical order-book depth is not available in parquet files.
- Uses current V6 unified playbook timings (MAIN entries only).
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

# Enable `python backtest_v6/sector_engine_v6.py` from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v6 import config
from v6.brain import (
    ExecutionFilters,
    MarketRegimeDetector,
    RiskManager,
    SafetyMonitor,
    SectorScore,
    SectorScorer,
    StockGrader,
    StockSignal,
)
from v6.data_engine import (
    calculate_atr,
    calculate_hma,
    calculate_rvol,
    calculate_slope,
    calculate_stoch_rsi,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SectorBacktesterV6")


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
    V6 backtester using current V6 production rules.
    """

    def __init__(
        self,
        data_root: Optional[Path] = None,
        starting_equity: Optional[float] = None,
        synthetic_spread_bps: float = 6.0,
        synthetic_circuit_pct: float = 0.10,
    ):
        self.data_root = Path(data_root) if data_root else self._default_data_root()
        self.daily_dir = self.data_root / "daily"
        self.intra_dir = self.data_root / "5minute"
        self.backtest_root = Path(__file__).parent
        self.history_dir = self.backtest_root / "history"

        self.synthetic_spread_bps = max(0.0, float(synthetic_spread_bps))
        self.synthetic_circuit_pct = max(0.01, float(synthetic_circuit_pct))

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

        # V6 strategy components
        self.regime_detector = MarketRegimeDetector()
        self.sector_scorer = SectorScorer()
        self.stock_grader = StockGrader()
        self.risk = RiskManager()
        self.safety = SafetyMonitor()

        # Portfolio state
        self.initial_equity = float(starting_equity or config.DEFAULT_PAPER_EQUITY)
        self.realized_pnl = 0.0
        self.active_trades: Dict[str, BacktestTrade] = {}
        self.trade_history: List[BacktestTrade] = []
        self.trade_counter = 0

        # Runtime state (mirrors v6/main.py fields used by strategy)
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

        # Run-history analytics buffers (auto-exported per run)
        self.run_id = ""
        self.run_started_at: Optional[datetime] = None
        self.run_finished_at: Optional[datetime] = None
        self.run_status = "NOT_STARTED"
        self.run_error = ""
        self.signal_counter = 0
        self.signal_records: List[Dict[str, Any]] = []
        self.position_records: List[Dict[str, Any]] = []
        self.all_signal_records: List[Dict[str, Any]] = []
        self.all_position_records: List[Dict[str, Any]] = []
        self.all_trade_records: List[Dict[str, Any]] = []
        self.all_trade_index_by_trade_id: Dict[str, int] = {}
        self.history_output_path: Optional[Path] = None
        self.history_file_date_label = ""
        self.history_file_time_label = ""

        self.initialized = False

    @staticmethod
    def _default_data_root() -> Path:
        return Path(__file__).parent / "data"

    def _log(self, msg: str):
        logger.info(msg)

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
        self.all_signal_records.clear()
        self.all_position_records.clear()
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
            "stage": trade.stage,
        }

    def _build_run_summary(self) -> Dict[str, Any]:
        final_equity = self.initial_equity + self.realized_pnl
        total_return = final_equity - self.initial_equity
        total_return_pct = ((final_equity / self.initial_equity) - 1.0) * 100.0 if self.initial_equity > 0 else 0.0

        constrained_signal_count = len(self.signal_records)
        constrained_position_count = len(self.position_records)
        executed_positions = sum(1 for row in self.position_records if row.get("executed_trade"))
        all_signal_count = len(self.all_signal_records)
        all_position_count = len(self.all_position_records)
        all_trade_count = len(self.all_trade_records)
        blocked_by_max_positions = sum(
            1 for row in self.all_position_records if row.get("blocked_by_max_positions")
        )
        max_slot_available_count = sum(
            1 for row in self.all_position_records if row.get("max_positions_slot_available")
        )

        risk_reason_counter = Counter(
            [row.get("risk_reason", "NA") for row in self.all_position_records if row.get("risk_reason")]
        )
        decision_counter = Counter(
            [row.get("entry_decision", "NA") for row in self.all_position_records if row.get("entry_decision")]
        )

        return {
            "initial_equity": float(self.initial_equity),
            "final_equity": float(final_equity),
            "total_return": float(total_return),
            "total_return_pct": float(total_return_pct),
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
        }

    def _ensure_history_output_path(self, start_date: date, end_date: date) -> Path:
        if self.history_output_path is not None:
            return self.history_output_path

        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp_dt = datetime.now()
        date_part = stamp_dt.strftime("%d-%m-%Y")
        time_display = stamp_dt.strftime("%I:%M %p").lower()

        # Keep filename Windows-safe while preserving requested format.
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
            "all_signal_records": self.all_signal_records,
            "all_position_records": self.all_position_records,
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
        # Recompute VWAP to guarantee availability and consistency.
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
        df = self.intra_data.get(symbol)
        if df is None or df.empty:
            return None, -1

        pos = df.index.searchsorted(ts)
        if pos >= len(df):
            return None, int(pos)
        if df.index[pos] != ts:
            return None, int(pos)
        return df.iloc[pos], int(pos)

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
        self.sector_scorer.select_top_n(ranked)
        self.sector_scores = ranked

    def _get_hma_alignment(
        self,
        symbol: str,
        current_price: float,
        intra_pos: int,
        daily_hist: pd.DataFrame,
    ) -> str:
        intra_df = self.intra_data.get(symbol)
        if intra_df is None or daily_hist is None:
            return "MIXED"
        if intra_pos <= 0:
            return "MIXED"

        closes_d = daily_hist["close"].to_numpy(dtype=float)
        closes_5m = intra_df.iloc[:intra_pos]["close"].to_numpy(dtype=float)
        if len(closes_d) < 20 or len(closes_5m) < 20:
            return "MIXED"

        series_d = np.append(closes_d, current_price)
        series_5m = np.append(closes_5m, current_price)

        hma9_curr = calculate_hma(series_d, 9)
        hma9_prev = calculate_hma(series_d[:-1], 9)
        hma20_curr = calculate_hma(series_5m, 20)
        hma20_prev = calculate_hma(series_5m[:-1], 20)

        h9_bull = current_price > hma9_curr and calculate_slope(hma9_curr, hma9_prev) == "UP"
        h20_bull = current_price > hma20_curr and calculate_slope(hma20_curr, hma20_prev) == "UP"
        h9_bear = current_price < hma9_curr and calculate_slope(hma9_curr, hma9_prev) == "DOWN"
        h20_bear = current_price < hma20_curr and calculate_slope(hma20_curr, hma20_prev) == "DOWN"

        if h9_bull and h20_bull:
            return "BULLISH"
        if h9_bear and h20_bear:
            return "BEARISH"
        return "MIXED"

    def _get_recent_rvol(self, symbol: str, intra_pos: int) -> float:
        intra_df = self.intra_data.get(symbol)
        if intra_df is None or intra_pos < 0:
            return 0.0
        volumes = intra_df.iloc[: intra_pos + 1]["volume"].to_numpy(dtype=float)
        if len(volumes) < 20:
            return 0.0
        recent = volumes[-20:]
        avg = float(np.mean(recent))
        last = float(recent[-1])
        return calculate_rvol(last, avg) if avg > 0 else 0.0

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

            daily_hist = self._get_daily_before(symbol, ts.date())
            if daily_hist is None or len(daily_hist) < 20:
                continue

            closes = daily_hist["close"].to_numpy(dtype=float)
            highs = daily_hist["high"].to_numpy(dtype=float)
            lows = daily_hist["low"].to_numpy(dtype=float)
            vols = daily_hist["volume"].to_numpy(dtype=float)

            adv = ExecutionFilters.calculate_adv_crores(closes, vols)
            if adv < config.MIN_ADV_CRORES:
                continue

            curr_price = float(row["close"])
            atr = calculate_atr(highs, lows, closes, period=10)
            if atr <= 0:
                continue

            bid, ask, u_circuit, l_circuit = self._synthetic_microstructure(symbol, curr_price, baselines)
            passed, gate_reason = ExecutionFilters.check_gate(
                bid=bid,
                ask=ask,
                price=curr_price,
                atr=atr,
                u_circuit=u_circuit,
                l_circuit=l_circuit,
            )
            spread_atr = (ask - bid) / atr if atr > 0 else 1.0

            hma_align = self._get_hma_alignment(symbol, curr_price, intra_pos, daily_hist)
            stoch_k, _ = calculate_stoch_rsi(np.append(closes, curr_price))
            rvol = self._get_recent_rvol(symbol, intra_pos)

            stock_sector_name = self.symbol_to_sector_name.get(symbol, "UNKNOWN")
            stock_sector_symbol = self.index_symbol_by_name.get(stock_sector_name, "")
            sec_score = sector_info.get(stock_sector_symbol)
            sec_rank = sec_score.rank if sec_score else 16
            sec_bias = sec_score.bias if sec_score else "NEUTRAL"

            signal = self.stock_grader.calculate_grade(
                hma_align=hma_align,
                rvol=rvol,
                stoch_k=stoch_k,
                sector_rank=sec_rank,
                spread_atr=spread_atr,
                vix_pctl=self.vix_percentile,
            )

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
            signal.price = curr_price
            stock_prev = baselines.get(symbol, {}).get("prev_close", 0.0)
            signal.change_pct = ((curr_price - stock_prev) / stock_prev * 100.0) if stock_prev > 0 else 0.0
            signal.gate_passed = passed
            signal.gate_reason = gate_reason
            self.active_signals.append(signal)

            if signal.grade in ("A+", "A"):
                self._process_entry(
                    signal=signal,
                    ltp=curr_price,
                    atr=atr,
                    ts=ts,
                    can_enter=can_enter,
                    gate_passed=passed,
                    gate_reason=gate_reason,
                    adv_crores=adv,
                    regime=regime,
                    scan_order=scan_order,
                )

    def _process_entry(
        self,
        signal: StockSignal,
        ltp: float,
        atr: float,
        ts: pd.Timestamp,
        can_enter: bool,
        gate_passed: bool,
        gate_reason: str,
        adv_crores: float,
        regime: str,
        scan_order: int,
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

        stop_dist = atr * config.STOP_ATR_MULT if atr > 0 else 0.0
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

        entry_decision = "NOT_EVALUATED"
        executed_trade = False
        executed_trade_id = ""

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
        elif not risk_allowed:
            entry_decision = f"RISK_REJECTED:{risk_reason}"
        else:
            self.trade_counter += 1
            trade_id = f"TRD_{signal.symbol}_{ts.strftime('%Y%m%d_%H%M')}_{self.trade_counter}"
            trade = BacktestTrade(
                trade_id=trade_id,
                symbol=signal.symbol,
                sector=signal.sector or "UNKNOWN",
                direction=signal.direction,
                entry_time=ts.to_pydatetime(),
                entry_price=float(ltp),
                initial_qty=int(sizing.shares),
                qty=int(sizing.shares),
                initial_stop=float(stop_price),
                current_stop=float(stop_price),
                target_1=float(target_1 or ltp),
                atr_at_entry=float(atr),
                highest_price=float(ltp),
                lowest_price=float(ltp),
            )
            self.active_trades[trade_id] = trade

            # Mirror live path: update in-memory exposure immediately.
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
            "rvol": float(signal.rvol),
            "stoch_k": float(signal.stoch_k),
            "sector_rank": int(signal.sector_rank),
            "spread_atr": float(signal.spread_atr),
            "gate_passed": bool(gate_passed),
            "gate_reason": gate_reason,
            "adv_crores": float(adv_crores),
            "atr": float(atr),
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
        }

        all_trade_id = executed_trade_id if executed_trade else f"POT_{signal_id}"
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
            "exit_reason": "" if executed_trade else entry_decision,
            "realized_pnl": 0.0,
            "stage": "ACTIVE" if executed_trade else "NOT_EXECUTED",
        }

        # Full opportunity universe: all A/A+ signals and their potential position/trade data.
        self.all_signal_records.append(signal_row)
        self.all_position_records.append(position_row)
        all_trade_idx = len(self.all_trade_records)
        self.all_trade_records.append(all_trade_row)
        if executed_trade and executed_trade_id:
            self.all_trade_index_by_trade_id[executed_trade_id] = all_trade_idx

        # Config-constrained dataset: only actual executed path.
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
            pnl = self._calculate_trade_pnl(trade.direction, trade.entry_price, exit_price, trade.qty)
            trade.realized_pnl += pnl
            self.realized_pnl += pnl
            trade.qty = 0

        trade.exit_time = ts.to_pydatetime()
        trade.exit_price = float(exit_price)
        trade.exit_reason = reason
        trade.stage = "CLOSED"

        # Keep all_trade_records schema identical to trade_records by updating
        # executed candidates with final close-state fields.
        all_idx = self.all_trade_index_by_trade_id.get(trade_id)
        if all_idx is not None and 0 <= all_idx < len(self.all_trade_records):
            self.all_trade_records[all_idx] = self._serialize_trade(trade)
            self.all_trade_index_by_trade_id.pop(trade_id, None)

        self.trade_history.append(copy.deepcopy(trade))
        self.active_trades.pop(trade_id, None)

    def _calculate_chandelier(self, trade: BacktestTrade, intra_pos: int) -> float:
        df = self.intra_data.get(trade.symbol)
        if df is None or intra_pos < 0:
            return trade.current_stop

        upto = df.iloc[: intra_pos + 1]
        if upto.empty:
            return trade.current_stop

        lookback = upto.tail(config.CHANDELIER_LOOKBACK)
        atr_buffer = trade.atr_at_entry * config.CHANDELIER_ATR_MULT
        if atr_buffer <= 0:
            return trade.current_stop

        if trade.direction == "LONG":
            anchor = max(float(lookback["high"].max()), float(trade.highest_price))
            return anchor - atr_buffer
        anchor = min(float(lookback["low"].min()), float(trade.lowest_price))
        return anchor + atr_buffer

    def _update_active_trades(self, ts: pd.Timestamp):
        for trade_id, trade in list(self.active_trades.items()):
            row, intra_pos = self._get_intra_row(trade.symbol, ts)
            if row is None:
                continue

            high = float(row["high"])
            low = float(row["low"])

            trade.highest_price = max(trade.highest_price, high)
            trade.lowest_price = min(trade.lowest_price, low)

            stop_hit = (
                trade.direction == "LONG" and low <= trade.current_stop
            ) or (
                trade.direction == "SHORT" and high >= trade.current_stop
            )
            if stop_hit:
                self._close_trade(trade_id, trade, ts, float(trade.current_stop), "STOP")
                continue

            if trade.stage == "ACTIVE":
                target_hit = (
                    trade.direction == "LONG" and high >= trade.target_1
                ) or (
                    trade.direction == "SHORT" and low <= trade.target_1
                )
                if target_hit:
                    partial_qty = max(1, int(trade.qty * config.TARGET_1_EXIT_PCT))
                    partial_qty = min(partial_qty, trade.qty)
                    partial_pnl = self._calculate_trade_pnl(
                        trade.direction,
                        trade.entry_price,
                        float(trade.target_1),
                        partial_qty,
                    )
                    trade.realized_pnl += partial_pnl
                    self.realized_pnl += partial_pnl
                    trade.qty -= partial_qty

                    if trade.qty <= 0:
                        self._close_trade(trade_id, trade, ts, float(trade.target_1), "TARGET1_FULL")
                        continue

                    trade.current_stop = trade.entry_price
                    trade.stage = "PARTIAL"

            if trade.stage == "PARTIAL":
                new_stop = self._calculate_chandelier(trade, intra_pos)
                if trade.direction == "LONG" and new_stop > trade.current_stop:
                    trade.current_stop = float(new_stop)
                if trade.direction == "SHORT" and new_stop < trade.current_stop:
                    trade.current_stop = float(new_stop)

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
        return current_equity, current_pnl, unrealized

    def _run_day(self, day: date) -> DayResult:
        self._daily_before_cache.clear()
        self._intraday_day_cache.clear()

        day_nifty = self._get_intraday_day("NIFTY 50", day)
        day_start_equity = self.initial_equity + self.realized_pnl

        if day_nifty.empty:
            return DayResult(day=day, start_equity=day_start_equity, end_equity=day_start_equity, pnl=0.0, trades=0)

        baselines = self._build_day_baselines(day)
        vix_window = self._get_vix_window(day)

        # Daily reset points
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

            # Breadth is wired as 0.0 in current live code path.
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
            self._force_exit_all(last_ts, reason="DAY_END_CLEANUP")
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

                # Incremental persistence: update the same history JSON daily.
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

        print("\n" + "=" * 80)
        print("V6 BACKTEST SUMMARY")
        print("-" * 80)
        print(f"Data Root:           {self.data_root}")
        print(f"Initial Equity:      {self.initial_equity:,.0f}")
        print(f"Final Equity:        {final_equity:,.0f}")
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

        print("=" * 80 + "\n")

    def export_trades(self, filepath: Optional[Path] = None):
        out_path = Path(filepath) if filepath else (self.data_root / "backtest_trades_v6.csv")
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
                    "realized_pnl": t.realized_pnl,
                    "stage": t.stage,
                    "exit_reason": t.exit_reason,
                }
            )

        pd.DataFrame(rows).to_csv(out_path, index=False)
        self._log(f"Exported {len(rows)} trades to {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V6 sector backtest engine")
    parser.add_argument("--start", type=str, default="2026-01-05", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2026-01-10", help="End date YYYY-MM-DD")
    parser.add_argument("--data-root", type=str, default=None, help="Data folder containing daily/ and 5minute/")
    parser.add_argument("--spread-bps", type=float, default=6.0, help="Synthetic bid/ask spread in basis points")
    parser.add_argument("--circuit-pct", type=float, default=0.10, help="Synthetic circuit band (fraction)")
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
    )
    engine.run_backtest(start, end)
    if args.export:
        export_path = Path(args.export_path) if args.export_path else None
        engine.export_trades(export_path)
