"""
V6.9 Advanced Backtest Analyzer  (v3)
======================================
Updated for V6.9 sector engine: HMA-based dynamic exit system,
signal quality gates, brokerage decomposition, and new trade fields.

Covers:
- Core trade stats with gross/net/charges decomposition
- HMA-based exit system analysis (HMA_CROSS_EXIT, STOP_HMA_TRAIL, etc.)
- V6.7 signal quality gate pass/fail funnel
- HMA quality metrics analysis (slope, separation, freshness, divergence)
- Direction alignment matrix
- Regime / VIX / timing performance
- Target/stop touch analysis
- Capital utilization
- First trade effect
- Bars-in-trade duration analysis (V6.9 field)

Usage:
    python analyze_backtest_v3.py                           # Latest history file
    python analyze_backtest_v3.py path/to/history.json      # Specific file
    python analyze_backtest_v3.py --latest --export          # Export JSON
"""

import argparse
import itertools
import json
import re
import sys
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(part: float, whole: float) -> float:
    return (part / whole * 100.0) if whole else 0.0


def _sign_to_dir(value: Any) -> str:
    v = _to_float(value, default=np.nan)
    if pd.isna(v):
        return "UNKNOWN"
    if v > 0:
        return "UP"
    if v < 0:
        return "DOWN"
    return "FLAT"


def _long_short_to_dir(value: Any) -> str:
    text = str(value or "").upper()
    if text == "LONG":
        return "UP"
    if text == "SHORT":
        return "DOWN"
    return "UNKNOWN"


def _numeric_summary(series: pd.Series) -> Dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {
            "count": 0, "mean": 0.0, "median": 0.0,
            "p10": 0.0, "p25": 0.0, "p75": 0.0, "p90": 0.0, "max": 0.0,
        }
    return {
        "count": int(s.shape[0]),
        "mean": round(float(s.mean()), 4),
        "median": round(float(s.median()), 4),
        "p10": round(float(s.quantile(0.10)), 4),
        "p25": round(float(s.quantile(0.25)), 4),
        "p75": round(float(s.quantile(0.75)), 4),
        "p90": round(float(s.quantile(0.90)), 4),
        "max": round(float(s.max()), 4),
    }


def _normalize_reason(text: Any) -> str:
    out = str(text or "NA")
    if "(" in out:
        out = out.split("(", 1)[0].strip()
    return out


class MarketDataProvider:
    def __init__(self, data_root: Optional[str]):
        self.data_root = Path(data_root) if data_root else None
        if self.data_root and not self.data_root.exists():
            fallback = Path(__file__).resolve().parent.parent / "data"
            self.data_root = fallback if fallback.exists() else self.data_root
        self.daily_dir = self.data_root / "daily" if self.data_root else None
        self.intra_dir = self.data_root / "5minute" if self.data_root else None
        self.available = bool(
            self.data_root
            and self.daily_dir
            and self.intra_dir
            and self.daily_dir.exists()
            and self.intra_dir.exists()
        )
        self.daily_cache: Dict[str, Optional[pd.DataFrame]] = {}
        self.intra_cache: Dict[str, Optional[pd.DataFrame]] = {}
        self.prev_close_cache: Dict[Tuple[str, datetime.date], Optional[float]] = {}
        self.last_error = ""

    @staticmethod
    def _prepare(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        out = df.copy()
        if not isinstance(out.index, pd.DatetimeIndex):
            for col in ["datetime", "timestamp", "date", "time"]:
                if col in out.columns:
                    out[col] = pd.to_datetime(out[col], errors="coerce")
                    out = out.dropna(subset=[col]).set_index(col)
                    break
        if not isinstance(out.index, pd.DatetimeIndex):
            return None
        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[~out.index.isna()].sort_index()
        return out if not out.empty else None

    def _load(self, folder: Path, symbol: str) -> Optional[pd.DataFrame]:
        path = folder / f"{symbol}.parquet"
        if not path.exists():
            return None
        try:
            return self._prepare(pd.read_parquet(path))
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def get_daily(self, symbol: str) -> Optional[pd.DataFrame]:
        if symbol not in self.daily_cache:
            self.daily_cache[symbol] = self._load(self.daily_dir, symbol) if self.available else None
        return self.daily_cache[symbol]

    def get_intra(self, symbol: str) -> Optional[pd.DataFrame]:
        if symbol not in self.intra_cache:
            self.intra_cache[symbol] = self._load(self.intra_dir, symbol) if self.available else None
        return self.intra_cache[symbol]

    def get_prev_close(self, symbol: str, day: datetime.date) -> Optional[float]:
        key = (symbol, day)
        if key in self.prev_close_cache:
            return self.prev_close_cache[key]
        ddf = self.get_daily(symbol)
        if ddf is None or "close" not in ddf.columns:
            self.prev_close_cache[key] = None
            return None
        prev = ddf[ddf.index.date < day]
        if prev.empty:
            self.prev_close_cache[key] = None
            return None
        val = _to_float(prev.iloc[-1]["close"], default=np.nan)
        self.prev_close_cache[key] = None if pd.isna(val) else val
        return self.prev_close_cache[key]

    def pct_from_prev_close(self, symbol: str, ts: pd.Timestamp) -> Optional[float]:
        prev = self.get_prev_close(symbol, pd.Timestamp(ts).date())
        if prev is None or prev <= 0:
            return None
        idf = self.get_intra(symbol)
        if idf is None or "close" not in idf.columns:
            return None
        ts = pd.Timestamp(ts)
        if ts in idf.index:
            row = idf.loc[ts]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            close = _to_float(row.get("close", np.nan), default=np.nan)
        else:
            up = idf[idf.index <= ts]
            if up.empty:
                return None
            close = _to_float(up.iloc[-1].get("close", np.nan), default=np.nan)
        if pd.isna(close):
            return None
        return (close - prev) / prev * 100.0

    def trade_window(self, symbol: str, entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> Optional[pd.DataFrame]:
        idf = self.get_intra(symbol)
        if idf is None:
            return None
        win = idf[(idf.index > pd.Timestamp(entry_ts)) & (idf.index <= pd.Timestamp(exit_ts))]
        return win if not win.empty else None


class AdvancedBacktestAnalyzerV3:
    """V6.9-aware backtest analyzer with HMA exit system and quality gate analytics."""

    def __init__(self, json_path: str, use_market_data: bool = True):
        self.json_path = Path(json_path)
        if not self.json_path.exists():
            raise FileNotFoundError(f"History file not found: {json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        self.run = self.data.get("run", {})
        self.summary = self.data.get("summary", {})
        self.config_snapshot = self.data.get("config_snapshot", {})
        self.daily_results = self.data.get("daily_results", [])
        self.trade_records = self.data.get("trade_records", [])
        self.signal_records = self.data.get("signal_records", [])
        self.position_records = self.data.get("position_records", [])
        self.all_trade_records = self.data.get("all_trade_records", [])

        self.market = MarketDataProvider(self.run.get("data_root")) if use_market_data else None
        self.daily_df = pd.DataFrame(self.daily_results)
        self.trade_df = self._build_trade_df()
        self.touch_df: Optional[pd.DataFrame] = None

    def _build_trade_df(self) -> pd.DataFrame:
        tdf = pd.DataFrame(self.trade_records)
        if tdf.empty:
            return tdf

        defaults = {
            "trade_id": "", "symbol": "", "sector": "UNKNOWN",
            "direction": "", "entry_time": None, "exit_time": None,
            "entry_price": 0.0, "initial_qty": 0, "realized_pnl": 0.0,
            "gross_pnl": 0.0, "total_turnover": 0.0, "total_charges": 0.0,
            "exit_reason": "", "stage": "CLOSED",
            # V6.1 fields
            "entry_risk_per_share": 0.0, "entry_atr_5m": 0.0,
            "mfe_r": 0.0, "mae_r": 0.0, "be_armed": False, "trail_armed": False,
            # V6.2
            "notional_at_entry": 0.0,
            # V6.4
            "index_direction": "", "sector_bias_at_entry": "", "signal_direction": "",
            # V6.9 HMA exit fields
            "hma_trail_active": False, "bars_in_trade": 0,
            "last_hma_fast": 0.0, "last_hma_slow": 0.0,
        }
        for col, val in defaults.items():
            if col not in tdf.columns:
                tdf[col] = val

        tdf["entry_time"] = pd.to_datetime(tdf["entry_time"], errors="coerce")
        tdf["exit_time"] = pd.to_datetime(tdf["exit_time"], errors="coerce")
        for c in ("entry_price", "realized_pnl", "gross_pnl", "total_turnover", "total_charges",
                   "entry_risk_per_share", "entry_atr_5m", "mfe_r", "mae_r",
                   "notional_at_entry", "last_hma_fast", "last_hma_slow"):
            tdf[c] = pd.to_numeric(tdf[c], errors="coerce").fillna(0.0)
        tdf["initial_qty"] = pd.to_numeric(tdf["initial_qty"], errors="coerce").fillna(0).astype(int)
        tdf["bars_in_trade"] = pd.to_numeric(tdf["bars_in_trade"], errors="coerce").fillna(0).astype(int)

        # Brokerage breakdown
        if "brokerage_breakdown" in tdf.columns:
            breakdown = pd.json_normalize(tdf["brokerage_breakdown"]).add_prefix("charge_")
            if not breakdown.empty:
                tdf = pd.concat([tdf.drop(columns=["brokerage_breakdown"]), breakdown], axis=1)
        for col in ("charge_brokerage", "charge_stt", "charge_transaction_charge",
                     "charge_sebi_charge", "charge_stamp_charge", "charge_gst"):
            if col not in tdf.columns:
                tdf[col] = 0.0
            tdf[col] = pd.to_numeric(tdf[col], errors="coerce").fillna(0.0)

        # Backward compat
        if np.isclose(float(tdf["gross_pnl"].abs().sum()), 0.0) and np.isclose(float(tdf["total_charges"].abs().sum()), 0.0):
            tdf["gross_pnl"] = tdf["realized_pnl"]

        tdf["entry_notional"] = tdf["entry_price"] * tdf["initial_qty"]
        tdf["entry_day"] = tdf["entry_time"].dt.date
        tdf["duration_min"] = (tdf["exit_time"] - tdf["entry_time"]).dt.total_seconds() / 60
        tdf["win"] = tdf["realized_pnl"] > 0

        # R-multiple
        total_risk = tdf["entry_risk_per_share"] * tdf["initial_qty"]
        tdf["r_multiple"] = np.where(total_risk.abs() > 0, tdf["realized_pnl"] / total_risk.abs(), 0)

        # Merge signal data
        sdf = pd.DataFrame(self.signal_records)
        if not sdf.empty and "executed_trade_id" in sdf.columns:
            sdf = sdf.copy()
            sdf["trade_id"] = sdf["executed_trade_id"].astype(str)
            sdf["timestamp"] = pd.to_datetime(sdf.get("timestamp"), errors="coerce")
            sdf = sdf.drop_duplicates(subset=["trade_id"], keep="last")
            rename = {c: f"sig_{c}" for c in sdf.columns if c != "trade_id"}
            sdf = sdf.rename(columns=rename)
            tdf = tdf.merge(sdf, on="trade_id", how="left")

        # Merge position data
        pdf = pd.DataFrame(self.position_records)
        if not pdf.empty and "executed_trade_id" in pdf.columns:
            pdf = pdf.copy()
            pdf["trade_id"] = pdf["executed_trade_id"].astype(str)
            pdf["timestamp"] = pd.to_datetime(pdf.get("timestamp"), errors="coerce")
            pdf = pdf.drop_duplicates(subset=["trade_id"], keep="last")
            rename = {c: f"pos_{c}" for c in pdf.columns if c != "trade_id"}
            pdf = pdf.rename(columns=rename)
            tdf = tdf.merge(pdf, on="trade_id", how="left")

        # Direction columns
        tdf["index_dir"] = tdf.get("sig_nifty_pct", pd.Series([np.nan] * len(tdf))).apply(_sign_to_dir)
        tdf["signal_dir"] = tdf.get("sig_direction", tdf["direction"]).apply(_long_short_to_dir)

        tdf["sector_pct"] = np.nan
        tdf["sector_dir_source"] = "SIGNAL_PROXY"
        if self.market and self.market.available:
            vals, src = [], []
            for row in tdf.itertuples(index=False):
                ts = getattr(row, "sig_timestamp", pd.NaT)
                ts = ts if not pd.isna(ts) else getattr(row, "entry_time", pd.NaT)
                sector = str(getattr(row, "sector", ""))
                pct = None if pd.isna(ts) else self.market.pct_from_prev_close(sector, pd.Timestamp(ts))
                vals.append(np.nan if pct is None else pct)
                src.append("MARKET_DATA" if pct is not None else "SIGNAL_PROXY")
            tdf["sector_pct"] = vals
            tdf["sector_dir_source"] = src

        tdf["sector_dir"] = tdf["sector_pct"].apply(_sign_to_dir)
        unknown = tdf["sector_dir"] == "UNKNOWN"
        tdf.loc[unknown, "sector_dir"] = tdf.loc[unknown, "signal_dir"]
        tdf.loc[unknown, "sector_dir_source"] = "SIGNAL_PROXY"

        # Extract HMA quality from signal records
        if "sig_hma_quality" in tdf.columns:
            hq = pd.json_normalize(tdf["sig_hma_quality"].apply(
                lambda x: x if isinstance(x, dict) else {}
            )).add_prefix("hq_")
            if not hq.empty:
                tdf = pd.concat([tdf.drop(columns=["sig_hma_quality"]), hq], axis=1)

        return tdf

    # ═══════════════════════════════════════════════════════════════════════════
    # Analysis Methods
    # ═══════════════════════════════════════════════════════════════════════════

    def _core_trade_stats(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"total_trades": 0}
        pnls = self.trade_df["realized_pnl"]
        pos = pnls[pnls > 0]
        neg = pnls[pnls < 0]
        gross_pnls = pd.to_numeric(self.trade_df.get("gross_pnl", pd.Series(0.0, index=self.trade_df.index)), errors="coerce").fillna(0.0)
        charges = pd.to_numeric(self.trade_df.get("total_charges", pd.Series(0.0, index=self.trade_df.index)), errors="coerce").fillna(0.0)
        total = int(pnls.shape[0])
        wins = int(pos.shape[0])
        losses = int(neg.shape[0])
        pf = (float(pos.sum()) / abs(float(neg.sum()))) if neg.shape[0] else float("inf")
        gross_total = float(gross_pnls.sum())
        total_charges = float(charges.sum())

        # R-multiple stats
        r_stats = {}
        if "r_multiple" in self.trade_df.columns:
            rm = self.trade_df["r_multiple"]
            r_stats = {
                "avg_r_multiple": round(float(rm.mean()), 3),
                "median_r_multiple": round(float(rm.median()), 3),
                "positive_r_trades": int((rm > 0).sum()),
                "negative_r_trades": int((rm < 0).sum()),
            }

        return {
            "total_trades": total,
            "wins": wins, "losses": losses,
            "breakeven": int((pnls == 0).sum()),
            "win_rate_pct": round(_pct(wins, total), 2),
            "net_pnl": round(float(pnls.sum()), 2),
            "gross_pnl_before_charges": round(gross_total, 2),
            "total_charges": round(total_charges, 2),
            "charges_as_pct_of_gross_pnl": round(_pct(total_charges, abs(gross_total)), 2) if gross_total != 0 else 0.0,
            "sum_positive_pnl": round(float(pos.sum()), 2) if not pos.empty else 0.0,
            "sum_negative_pnl": round(float(neg.sum()), 2) if not neg.empty else 0.0,
            "avg_trade_pnl": round(float(pnls.mean()), 2),
            "best_trade": round(float(pnls.max()), 2),
            "worst_trade": round(float(pnls.min()), 2),
            "profit_factor": round(pf, 2) if np.isfinite(pf) else "Inf",
            **r_stats,
        }

    def _core_equity(self) -> Dict[str, Any]:
        ini = _to_float(self.summary.get("initial_equity", 0.0))
        fin = _to_float(self.summary.get("final_equity", ini))
        ret = _to_float(self.summary.get("total_return", fin - ini))
        ret_pct = _to_float(self.summary.get("total_return_pct", _pct(fin - ini, ini)))
        gross_ret = _to_float(self.summary.get("gross_return_before_charges", ret + _to_float(self.summary.get("total_charges", 0.0))))

        curve = [ini]
        sorted_pnls = self.trade_df.sort_values("exit_time")["realized_pnl"] if not self.trade_df.empty else pd.Series(dtype=float)
        for pnl in sorted_pnls.tolist():
            curve.append(curve[-1] + float(pnl))
        peak = ini
        max_dd, max_dd_pct = 0.0, 0.0
        for eq in curve:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = peak - eq
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = dd / peak * 100.0

        return {
            "initial_equity": round(ini, 2),
            "final_equity": round(fin, 2),
            "total_return": round(ret, 2),
            "total_return_pct": round(ret_pct, 2),
            "gross_return_before_charges": round(gross_ret, 2),
            "max_drawdown_inr": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
        }

    def _execution(self) -> Dict[str, Any]:
        all_signals = int(_to_float(self.summary.get("all_a_grade_signals", 0)))
        if all_signals <= 0:
            all_signals = len(self.all_trade_records) or len(self.signal_records)
        executed = int(_to_float(self.summary.get("executed_positions", 0)))
        if executed <= 0:
            executed = len(self.signal_records) or int(self.trade_df.shape[0])

        return {
            "all_a_grade_signals": all_signals,
            "executed_signals": executed,
            "execution_rate_pct": round(_pct(executed, all_signals), 2),
            "blocked_by_max_positions": int(_to_float(self.summary.get("blocked_by_max_positions_count", 0))),
            "capital_blocked": int(_to_float(self.summary.get("capital_blocked_count", 0))),
            "alignment_blocked": int(_to_float(self.summary.get("alignment_blocked_count", 0))),
        }

    def _daily(self) -> Dict[str, Any]:
        if self.daily_df.empty:
            return {"total_trading_days": 0}
        pnls = pd.to_numeric(self.daily_df.get("pnl", 0), errors="coerce").fillna(0.0)
        return {
            "total_trading_days": int(self.daily_df.shape[0]),
            "positive_days": int((pnls > 0).sum()),
            "negative_days": int((pnls < 0).sum()),
            "breakeven_days": int((pnls == 0).sum()),
            "best_day": round(float(pnls.max()), 2),
            "worst_day": round(float(pnls.min()), 2),
            "avg_daily_pnl": round(float(pnls.mean()), 2),
        }

    def _brokerage(self) -> Dict[str, Any]:
        exchange = (
            self.summary.get("exchange")
            or self.data.get("inputs", {}).get("exchange")
            or self.config_snapshot.get("V6_8_EXCHANGE")
            or "UNKNOWN"
        )
        transaction_charge_pct = _to_float(
            self.summary.get("transaction_charge_pct",
                             self.data.get("inputs", {}).get("transaction_charge_pct")),
            default=0.0,
        )
        trade_count = int(self.trade_df.shape[0]) if not self.trade_df.empty else 0
        total_turnover = _to_float(self.summary.get("total_turnover"), default=np.nan)
        total_charges = _to_float(self.summary.get("total_charges"), default=np.nan)

        if (pd.isna(total_turnover) or total_turnover <= 0) and not self.trade_df.empty:
            total_turnover = float(pd.to_numeric(self.trade_df.get("total_turnover", 0.0), errors="coerce").fillna(0.0).sum())
        if (pd.isna(total_charges) or total_charges <= 0) and not self.trade_df.empty:
            total_charges = float(pd.to_numeric(self.trade_df.get("total_charges", 0.0), errors="coerce").fillna(0.0).sum())

        summary_breakdown = self.summary.get("brokerage_breakdown") or {}
        trade_breakdown = {}
        if not self.trade_df.empty:
            for k in ("brokerage", "stt", "transaction_charge", "sebi_charge", "stamp_charge", "gst"):
                col = f"charge_{k}"
                trade_breakdown[k] = float(pd.to_numeric(self.trade_df.get(col, 0.0), errors="coerce").fillna(0.0).sum())
        breakdown = {
            k: round(_to_float(summary_breakdown.get(k), default=trade_breakdown.get(k, 0.0)), 2)
            for k in ("brokerage", "stt", "transaction_charge", "sebi_charge", "stamp_charge", "gst")
        }

        return {
            "exchange": str(exchange),
            "transaction_charge_pct": round(transaction_charge_pct, 5),
            "total_turnover": round(float(total_turnover or 0.0), 2),
            "total_charges": round(float(total_charges or 0.0), 2),
            "charges_pct_of_turnover": round(_pct(float(total_charges or 0.0), float(total_turnover or 0.0)), 4),
            "avg_charge_per_trade": round((float(total_charges or 0.0) / trade_count), 4) if trade_count else 0.0,
            "breakdown": breakdown,
        }

    def _hma_exit_analysis(self) -> Dict[str, Any]:
        """V6.9-specific: Analyze HMA-based exit system performance."""
        if self.trade_df.empty:
            return {"available": False}

        df = self.trade_df.copy()
        exit_reasons = df["exit_reason"].value_counts().to_dict()

        # Group exit reasons into categories
        hma_exit_categories = {
            "HMA_CROSS_EXIT": "Signal reversal (HMA cross)",
            "STOP_HMA_TRAIL": "HMA trailing stop hit",
            "STOP_HARD": "Initial hard stop hit",
            "TARGET1_FULL": "Full target exit (all qty at T1)",
            "FORCE_EXIT": "End-of-day force exit",
            "SAFETY_HALT": "Safety monitor halt",
        }

        exit_analysis = []
        for reason, g in df.groupby("exit_reason"):
            trades = int(g.shape[0])
            wins = int((g["realized_pnl"] > 0).sum())
            desc = hma_exit_categories.get(reason, reason)
            exit_analysis.append({
                "exit_reason": reason,
                "description": desc,
                "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "net_pnl": round(float(g["realized_pnl"].sum()), 2),
                "avg_pnl": round(float(g["realized_pnl"].mean()), 2),
                "avg_bars_in_trade": round(float(g["bars_in_trade"].mean()), 1),
                "avg_duration_min": round(float(g["duration_min"].mean()), 1),
                "avg_mfe_r": round(float(g["mfe_r"].mean()), 2),
                "avg_mae_r": round(float(g["mae_r"].mean()), 2),
            })

        # HMA trail stats
        hma_trail_count = int(df["hma_trail_active"].sum())
        be_armed_count = int(df["be_armed"].sum())
        partial_exits = int((df["stage"] == "PARTIAL").sum()) + int((df["exit_reason"] == "TARGET1_FULL").sum())

        # Bars in trade analysis
        bars_summary = _numeric_summary(df["bars_in_trade"])

        return {
            "available": True,
            "exit_reason_counts": exit_reasons,
            "exit_reason_analysis": sorted(exit_analysis, key=lambda x: x["trades"], reverse=True),
            "hma_trail_activated": hma_trail_count,
            "hma_trail_pct": round(_pct(hma_trail_count, len(df)), 2),
            "be_armed_count": be_armed_count,
            "be_armed_pct": round(_pct(be_armed_count, len(df)), 2),
            "partial_profit_takes": partial_exits,
            "bars_in_trade_summary": bars_summary,
        }

    def _quality_gate_analysis(self) -> Dict[str, Any]:
        """V6.7/V6.9: Analyze signal quality gate pass/fail rates."""
        gate_stats = {
            "gate_slope_blocked": int(_to_float(self.summary.get("gate_slope_blocked", 0))),
            "gate_freshness_blocked": int(_to_float(self.summary.get("gate_freshness_blocked", 0))),
            "gate_price_align_blocked": int(_to_float(self.summary.get("gate_price_align_blocked", 0))),
            "gate_separation_blocked": int(_to_float(self.summary.get("gate_separation_blocked", 0))),
            "gate_divergence_blocked": int(_to_float(self.summary.get("gate_divergence_blocked", 0))),
        }
        total_blocked = sum(gate_stats.values())
        gate_stats["total_gate_rejections"] = total_blocked

        # HMA quality metrics on executed trades
        hq_analysis = {}
        if not self.trade_df.empty:
            for col in ("hq_slope_fast", "hq_slope_slow", "hq_cross_bars_ago",
                         "hq_separation", "hq_sep_atr_frac"):
                if col in self.trade_df.columns:
                    hq_analysis[col] = _numeric_summary(self.trade_df[col])
            if "hq_is_diverging" in self.trade_df.columns:
                div_count = int(self.trade_df["hq_is_diverging"].sum())
                hq_analysis["diverging_pct"] = round(_pct(div_count, len(self.trade_df)), 2)

        # HMA config
        hma_config = {
            "HMA_FAST": self.config_snapshot.get("V6_6_HMA_FAST"),
            "HMA_SLOW": self.config_snapshot.get("V6_6_HMA_SLOW"),
            "CROSS_FRESHNESS_BARS": self.config_snapshot.get("V6_7_CROSS_FRESHNESS_BARS"),
            "SLOPE_LOOKBACK": self.config_snapshot.get("V6_7_SLOPE_LOOKBACK"),
            "SLOPE_MIN_PCT": self.config_snapshot.get("V6_7_SLOPE_MIN_PCT"),
            "MIN_HMA_SEP_ATR_FRAC": self.config_snapshot.get("V6_7_MIN_HMA_SEP_ATR_FRAC"),
            "DIVERGENCE_LOOKBACK": self.config_snapshot.get("V6_7_DIVERGENCE_LOOKBACK"),
        }

        return {
            "gate_rejection_stats": gate_stats,
            "hma_quality_on_executed": hq_analysis,
            "hma_config": hma_config,
        }

    def _v69_exit_config(self) -> Dict[str, Any]:
        """V6.9 exit system configuration from config snapshot."""
        return {
            "STOP_ATR_MULT_5M": self.config_snapshot.get("V6_9_STOP_ATR_MULT_5M"),
            "STOP_MIN_PCT": self.config_snapshot.get("V6_9_STOP_MIN_PCT"),
            "HMA_TRAIL_BUFFER_ATR": self.config_snapshot.get("V6_9_HMA_TRAIL_BUFFER_ATR"),
            "TARGET_1_R": self.config_snapshot.get("V6_9_TARGET_1_R"),
            "TARGET_1_EXIT_PCT": self.config_snapshot.get("V6_9_TARGET_1_EXIT_PCT"),
        }

    def _blockers(self) -> Dict[str, Any]:
        raw_dec = self.summary.get("decision_counts") or Counter(
            x.get("entry_decision", "NA") for x in self.position_records if x.get("entry_decision")
        )
        raw_risk = self.summary.get("risk_reason_counts") or Counter(
            x.get("risk_reason", "NA") for x in self.position_records if x.get("risk_reason")
        )
        dec_norm = Counter()
        for k, v in raw_dec.items():
            dec_norm[_normalize_reason(k)] += int(v)
        risk_norm = Counter()
        for k, v in raw_risk.items():
            risk_norm[_normalize_reason(k)] += int(v)
        return {
            "decision_breakdown": dict(raw_dec),
            "risk_reason_breakdown": dict(raw_risk),
            "decision_breakdown_normalized": dict(dec_norm),
            "risk_reason_breakdown_normalized": dict(risk_norm),
        }

    def direction_matrix(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"rows": []}
        df = self.trade_df.copy()
        valid = df[
            df["index_dir"].isin(["UP", "DOWN"])
            & df["sector_dir"].isin(["UP", "DOWN"])
            & df["signal_dir"].isin(["UP", "DOWN"])
        ]
        rows = []
        for i, s, g in itertools.product(["UP", "DOWN"], ["UP", "DOWN"], ["UP", "DOWN"]):
            sub = valid[
                (valid["index_dir"] == i) & (valid["sector_dir"] == s) & (valid["signal_dir"] == g)
            ]
            trades = int(sub.shape[0])
            wins = int((sub["realized_pnl"] > 0).sum())
            pos_pnl = sub.loc[sub["realized_pnl"] > 0, "realized_pnl"]
            neg_pnl = sub.loc[sub["realized_pnl"] < 0, "realized_pnl"]
            rows.append({
                "index_dir": i, "sector_dir": s, "signal_dir": g,
                "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "sum_positive_pnl": round(float(pos_pnl.sum()), 2) if not pos_pnl.empty else 0.0,
                "sum_negative_pnl": round(float(neg_pnl.sum()), 2) if not neg_pnl.empty else 0.0,
                "net_pnl": round(float(sub["realized_pnl"].sum()) if trades else 0.0, 2),
            })
        aligned = valid[
            (valid["index_dir"] == valid["sector_dir"]) & (valid["sector_dir"] == valid["signal_dir"])
        ]
        return {
            "rows": rows,
            "total_trades_considered": int(valid.shape[0]),
            "excluded_trades": int(df.shape[0] - valid.shape[0]),
            "sector_direction_source_counts": dict(Counter(df.get("sector_dir_source", pd.Series(dtype=str)))),
            "aligned_win_rate_pct": round(_pct(int((aligned["realized_pnl"] > 0).sum()), int(aligned.shape[0])), 2),
        }

    def risk_target_analysis(self) -> Dict[str, Any]:
        if self.trade_df.empty or "pos_stop_price" not in self.trade_df.columns:
            return {"available": False, "reason": "Position-level executed data missing"}
        df = self.trade_df.copy()
        df["stop_price"] = pd.to_numeric(df["pos_stop_price"], errors="coerce")
        df["target_1"] = pd.to_numeric(df["pos_target_1"], errors="coerce")
        df["stop_dist"] = (df["entry_price"] - df["stop_price"]).abs()
        df["target_dist"] = (df["target_1"] - df["entry_price"]).abs()
        df["stop_pct"] = np.where(df["entry_price"] > 0, df["stop_dist"] / df["entry_price"] * 100.0, np.nan)
        df["target_pct"] = np.where(df["entry_price"] > 0, df["target_dist"] / df["entry_price"] * 100.0, np.nan)
        df["t_s_ratio"] = np.where(df["stop_dist"] > 0, df["target_dist"] / df["stop_dist"], np.nan)
        df["planned_risk_inr"] = df["stop_dist"] * df["initial_qty"]
        df["realized_r"] = np.where(df["planned_risk_inr"] > 0, df["realized_pnl"] / df["planned_risk_inr"], np.nan)

        by_dir = []
        for d, g in df.groupby("direction"):
            by_dir.append({
                "direction": str(d),
                "trades": int(g.shape[0]),
                "avg_stop_pct": round(float(g["stop_pct"].mean()), 4),
                "avg_target_pct": round(float(g["target_pct"].mean()), 4),
                "avg_t_s_ratio": round(float(g["t_s_ratio"].mean()), 4),
                "avg_realized_r": round(float(g["realized_r"].mean()), 4),
                "win_rate_pct": round(_pct(int((g["realized_pnl"] > 0).sum()), int(g.shape[0])), 2),
            })

        # By exit reason
        by_exit = []
        for reason, g in df.groupby("exit_reason"):
            by_exit.append({
                "exit_reason": str(reason),
                "trades": int(g.shape[0]),
                "avg_realized_r": round(float(g["realized_r"].mean()), 4),
                "avg_mfe_r": round(float(g["mfe_r"].mean()), 3),
                "avg_mae_r": round(float(g["mae_r"].mean()), 3),
            })

        return {
            "available": True,
            "summary_stop_pct": _numeric_summary(df["stop_pct"]),
            "summary_target_pct": _numeric_summary(df["target_pct"]),
            "summary_t_s_ratio": _numeric_summary(df["t_s_ratio"]),
            "summary_realized_r": _numeric_summary(df["realized_r"]),
            "summary_mfe_r": _numeric_summary(df["mfe_r"]),
            "summary_mae_r": _numeric_summary(df["mae_r"]),
            "by_direction": by_dir,
            "by_exit_reason": sorted(by_exit, key=lambda x: x["trades"], reverse=True),
        }

    def target_stop_touch_analysis(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"available": False, "reason": "No trades"}
        if not self.market or not self.market.available:
            return {"available": False, "reason": "Market data not available"}
        if "pos_stop_price" not in self.trade_df.columns:
            return {"available": False, "reason": "Position stop/target not available"}

        rows = []
        for row in self.trade_df.itertuples(index=False):
            symbol = str(getattr(row, "symbol", ""))
            direction = str(getattr(row, "direction", "")).upper()
            entry_ts = getattr(row, "entry_time", pd.NaT)
            exit_ts = getattr(row, "exit_time", pd.NaT)
            stop = _to_float(getattr(row, "pos_stop_price", np.nan), default=np.nan)
            target = _to_float(getattr(row, "pos_target_1", np.nan), default=np.nan)
            pnl = _to_float(getattr(row, "realized_pnl", 0.0), default=0.0)

            if not symbol or pd.isna(entry_ts) or pd.isna(exit_ts) or pd.isna(stop) or pd.isna(target):
                rows.append({"trade_id": getattr(row, "trade_id", ""), "first_touch": "NO_DATA", "pnl": pnl})
                continue

            win = self.market.trade_window(symbol, pd.Timestamp(entry_ts), pd.Timestamp(exit_ts))
            if win is None or "high" not in win.columns or "low" not in win.columns:
                rows.append({"trade_id": getattr(row, "trade_id", ""), "first_touch": "NO_DATA", "pnl": pnl})
                continue

            if direction == "LONG":
                target_hits = win[win["high"] >= target]
                stop_hits = win[win["low"] <= stop]
            elif direction == "SHORT":
                target_hits = win[win["low"] <= target]
                stop_hits = win[win["high"] >= stop]
            else:
                target_hits = win.iloc[0:0]
                stop_hits = win.iloc[0:0]

            t_ts = target_hits.index[0] if not target_hits.empty else pd.NaT
            s_ts = stop_hits.index[0] if not stop_hits.empty else pd.NaT

            if not pd.isna(t_ts) and not pd.isna(s_ts):
                first = "TARGET_FIRST" if t_ts < s_ts else "STOP_FIRST" if s_ts < t_ts else "SAME_BAR_BOTH"
            elif not pd.isna(t_ts):
                first = "TARGET_ONLY"
            elif not pd.isna(s_ts):
                first = "STOP_ONLY"
            else:
                first = "NONE"

            rows.append({"trade_id": getattr(row, "trade_id", ""), "first_touch": first, "pnl": pnl})

        tdf = pd.DataFrame(rows)
        self.touch_df = tdf
        total = int(tdf.shape[0])
        counts = Counter(tdf["first_touch"].tolist())
        perf = []
        for cat, g in tdf.groupby("first_touch"):
            trades = int(g.shape[0])
            wins = int((g["pnl"] > 0).sum())
            perf.append({
                "first_touch": str(cat), "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "pnl": round(float(g["pnl"].sum()), 2),
            })

        return {
            "available": True,
            "total_trades_checked": total,
            "first_touch_breakdown": {
                k: {"count": int(v), "pct": round(_pct(v, total), 2)}
                for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
            },
            "first_touch_performance": sorted(perf, key=lambda x: x["trades"], reverse=True),
        }

    def capital_utilization(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"summary": {}}

        daily_start, daily_pnl = {}, {}
        ddf = self.daily_df.copy()
        if not ddf.empty and "day" in ddf.columns:
            ddf["day"] = pd.to_datetime(ddf["day"], errors="coerce").dt.date
            for row in ddf.itertuples(index=False):
                daily_start[getattr(row, "day")] = _to_float(getattr(row, "start_equity", np.nan), default=np.nan)
                daily_pnl[getattr(row, "day")] = _to_float(getattr(row, "pnl", np.nan), default=np.nan)

        rows = []
        for day, g in self.trade_df.groupby("entry_day"):
            if pd.isna(day):
                continue
            events = []
            for r in g.itertuples(index=False):
                notional = _to_float(getattr(r, "entry_notional", 0.0), default=0.0)
                if notional <= 0:
                    continue
                et = getattr(r, "entry_time", pd.NaT)
                xt = getattr(r, "exit_time", pd.NaT)
                if not pd.isna(et):
                    events.append((pd.Timestamp(et), 1, notional))
                if not pd.isna(xt):
                    events.append((pd.Timestamp(xt), 0, -notional))
            events.sort(key=lambda x: (x[0], x[1]))
            current, peak = 0.0, 0.0
            for _, _, delta in events:
                current = max(0.0, current + delta)
                peak = max(peak, current)

            start_eq = daily_start.get(day, np.nan)
            rows.append({
                "day": str(day), "trades": int(g.shape[0]),
                "start_equity": round(start_eq, 2) if not pd.isna(start_eq) else None,
                "day_pnl": round(daily_pnl.get(day, float(g["realized_pnl"].sum())), 2),
                "total_entry_notional": round(float(g["entry_notional"].sum()), 2),
                "peak_deployed_notional": round(peak, 2),
                "peak_utilization_pct": round(_pct(peak, start_eq), 2) if (not pd.isna(start_eq) and start_eq > 0) else None,
            })

        if not rows:
            return {"summary": {}}

        rdf = pd.DataFrame(rows)
        return {"summary": {
            "days_with_trades": int(rdf.shape[0]),
            "avg_peak_deployed_notional": round(float(rdf["peak_deployed_notional"].mean()), 2),
            "max_peak_deployed_notional": round(float(rdf["peak_deployed_notional"].max()), 2),
            "avg_peak_utilization_pct": round(float(pd.to_numeric(rdf["peak_utilization_pct"], errors="coerce").mean()), 2),
            "peak_utilization_from_summary": round(_to_float(self.summary.get("peak_utilization_pct", 0.0)), 2),
        }}

    def first_trade_effect(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"rows": [], "correlation": None}

        ddf = self.daily_df.copy()
        day_pnl_map = {}
        if not ddf.empty and "day" in ddf.columns:
            ddf["day"] = pd.to_datetime(ddf["day"], errors="coerce").dt.date
            for r in ddf.itertuples(index=False):
                day_pnl_map[getattr(r, "day")] = _to_float(getattr(r, "pnl", 0.0))

        rows = []
        for day, g in self.trade_df.groupby("entry_day"):
            if pd.isna(day):
                continue
            g = g.sort_values(by=["entry_time", "trade_id"])
            first = g.iloc[0]
            fpnl = float(first["realized_pnl"])
            label = "FIRST_WIN" if fpnl > 0 else "FIRST_LOSS" if fpnl < 0 else "FIRST_BREAKEVEN"
            day_pnl = day_pnl_map.get(day, float(g["realized_pnl"].sum()))
            rows.append({
                "day": str(day), "first_trade_outcome": label,
                "first_trade_pnl": round(fpnl, 2),
                "day_pnl": round(day_pnl, 2),
                "day_profit": bool(day_pnl > 0),
            })

        if not rows:
            return {"rows": [], "correlation": None}

        rdf = pd.DataFrame(rows)
        summary_rows = []
        for label, g in rdf.groupby("first_trade_outcome"):
            matching_days = set(pd.to_datetime(g["day"], errors="coerce").dt.date)
            trades_on_matching_days = self.trade_df[self.trade_df["entry_day"].isin(matching_days)]
            pnls = trades_on_matching_days["realized_pnl"]
            pos_pnl = pnls[pnls > 0]
            neg_pnl = pnls[pnls < 0]
            total_trades = int(pnls.shape[0])
            wins = int((pnls > 0).sum())
            summary_rows.append({
                "first_trade_outcome": str(label),
                "days": int(g.shape[0]),
                "day_profit_rate_pct": round(_pct(int(g["day_profit"].sum()), int(g.shape[0])), 2),
                "avg_day_pnl": round(float(g["day_pnl"].mean()), 2),
                "median_day_pnl": round(float(g["day_pnl"].median()), 2),
                "win_rate_pct": round(_pct(wins, total_trades), 2),
                "net_pnl": round(float(pnls.sum()), 2),
            })

        corr = None
        if rdf["first_trade_pnl"].nunique() > 1 and rdf["day_pnl"].nunique() > 1:
            corr = round(float(rdf["first_trade_pnl"].corr(rdf["day_pnl"])), 4)

        return {"rows": sorted(summary_rows, key=lambda x: x["days"], reverse=True), "correlation": corr}

    def regime_performance(self) -> Dict[str, Any]:
        if self.trade_df.empty or "sig_regime" not in self.trade_df.columns:
            return {"rows": []}
        rows = []
        for regime, g in self.trade_df.groupby("sig_regime"):
            trades = int(g.shape[0])
            wins = int((g["realized_pnl"] > 0).sum())
            rows.append({
                "regime": str(regime), "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "pnl": round(float(g["realized_pnl"].sum()), 2),
                "avg_pnl": round(float(g["realized_pnl"].mean()), 2),
            })
        return {"rows": sorted(rows, key=lambda x: x["trades"], reverse=True)}

    def time_bucket_performance(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"rows": []}
        df = self.trade_df.copy()

        def bucket(ts: Any) -> str:
            if pd.isna(ts):
                return "UNKNOWN"
            t = pd.Timestamp(ts).time()
            if t < time(10, 30):
                return "OPEN_0925_1030"
            if t < time(12, 0):
                return "MID_1030_1200"
            if t < time(13, 15):
                return "LUNCH_1200_1315"
            if t <= time(14, 5):
                return "AFTERNOON_1315_1405"
            return "POST_1405"

        df["bucket"] = df["entry_time"].apply(bucket)
        rows = []
        for b, g in df.groupby("bucket"):
            trades = int(g.shape[0])
            wins = int((g["realized_pnl"] > 0).sum())
            rows.append({
                "bucket": str(b), "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "pnl": round(float(g["realized_pnl"].sum()), 2),
                "avg_pnl": round(float(g["realized_pnl"].mean()), 2),
            })
        return {"rows": sorted(rows, key=lambda x: x["trades"], reverse=True)}

    def sector_performance(self) -> Dict[str, Any]:
        """Per-sector breakdown with exit reason decomposition."""
        if self.trade_df.empty or "sector" not in self.trade_df.columns:
            return {"rows": []}
        rows = []
        for sector, g in self.trade_df.groupby("sector"):
            trades = int(g.shape[0])
            wins = int((g["realized_pnl"] > 0).sum())
            exit_breakdown = dict(g["exit_reason"].value_counts())
            rows.append({
                "sector": str(sector), "trades": trades,
                "win_rate_pct": round(_pct(wins, trades), 2),
                "net_pnl": round(float(g["realized_pnl"].sum()), 2),
                "avg_pnl": round(float(g["realized_pnl"].mean()), 2),
                "avg_bars": round(float(g["bars_in_trade"].mean()), 1),
                "exit_breakdown": exit_breakdown,
            })
        return {"rows": sorted(rows, key=lambda x: x["net_pnl"], reverse=True)}

    def symbol_performance(self) -> Dict[str, Any]:
        """Per-symbol breakdown — top winners and losers."""
        if self.trade_df.empty:
            return {"top_winners": [], "top_losers": []}
        sp = self.trade_df.groupby("symbol", as_index=False).agg(
            trades=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            avg_bars=("bars_in_trade", "mean"),
        )
        sp["avg_bars"] = sp["avg_bars"].round(1)
        top_w = sp.nlargest(10, "net_pnl").to_dict("records")
        top_l = sp.nsmallest(10, "net_pnl").to_dict("records")
        return {"top_winners": top_w, "top_losers": top_l}

    def build_analysis(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "analysis_date": datetime.now().isoformat(),
                "history_file": str(self.json_path),
                "run_id": self.run.get("run_id"),
                "run_status": self.run.get("status"),
                "start_date": self.run.get("start_date"),
                "end_date": self.run.get("end_date"),
                "market_data_available": bool(self.market and self.market.available),
                "market_data_error": self.market.last_error if self.market else "",
                "engine_version": "V6.9 (HMA-based exit system)",
            },
            "v69_exit_config": self._v69_exit_config(),
            "trade_statistics": self._core_trade_stats(),
            "equity_analysis": self._core_equity(),
            "execution_metrics": self._execution(),
            "brokerage_analysis": self._brokerage(),
            "hma_exit_analysis": self._hma_exit_analysis(),
            "quality_gate_analysis": self._quality_gate_analysis(),
            "blocker_analysis": self._blockers(),
            "daily_performance": self._daily(),
            "direction_matrix_index_sector_signal": self.direction_matrix(),
            "risk_target_analysis": self.risk_target_analysis(),
            "target_stop_touch_analysis": self.target_stop_touch_analysis(),
            "capital_utilization": self.capital_utilization(),
            "first_trade_effect": self.first_trade_effect(),
            "regime_performance": self.regime_performance(),
            "time_bucket_performance": self.time_bucket_performance(),
            "sector_performance": self.sector_performance(),
            "symbol_performance": self.symbol_performance(),
        }

    @staticmethod
    def _print_table(title: str, rows: List[Dict[str, Any]], cols: List[Tuple[str, str]], max_rows: Optional[int] = None):
        print(f"\n{title}")
        if not rows:
            print("  (no data)")
            return
        use = rows[:max_rows or len(rows)]

        def fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.2f}"
            if isinstance(v, dict):
                return str(v)
            return str(v)

        widths = {k: len(h) for k, h in cols}
        for row in use:
            for k, _ in cols:
                widths[k] = max(widths[k], len(fmt(row.get(k, ""))))
        header = "  " + " | ".join(h.ljust(widths[k]) for k, h in cols)
        sep = "  " + "-+-".join("-" * widths[k] for k, _ in cols)
        print(header)
        print(sep)
        for row in use:
            print("  " + " | ".join(fmt(row.get(k, "")).ljust(widths[k]) for k, _ in cols))

    def print_report(self, top: int = 10) -> Dict[str, Any]:
        out = self.build_analysis()
        line = "=" * 110
        print("\n" + line)
        print("V6.9 ADVANCED BACKTEST ANALYSIS (HMA-Based Exit System)")
        print(line)

        m = out["metadata"]
        print(f"Run: {m.get('run_id')} | {m.get('run_status')} | {m.get('start_date')} -> {m.get('end_date')}")
        print(f"History: {m.get('history_file')}")
        print(f"Market data available: {m.get('market_data_available')}")

        # V6.9 exit config
        ec = out["v69_exit_config"]
        print(f"\nV6.9 Exit Config: STOP={ec.get('STOP_ATR_MULT_5M')}×ATR_5m | "
              f"HMA_TRAIL_BUFFER={ec.get('HMA_TRAIL_BUFFER_ATR')}×ATR | "
              f"TARGET={ec.get('TARGET_1_R')}R @{ec.get('TARGET_1_EXIT_PCT', 0)*100:.0f}%")

        # HMA config
        qg = out["quality_gate_analysis"]
        hc = qg.get("hma_config", {})
        print(f"HMA Config: FAST={hc.get('HMA_FAST')} SLOW={hc.get('HMA_SLOW')} "
              f"FRESHNESS={hc.get('CROSS_FRESHNESS_BARS')} bars")

        print("\n--- Core Stats ---")
        print("  Trade Stats:", out["trade_statistics"])
        print("  Equity:", out["equity_analysis"])
        print("  Execution:", out["execution_metrics"])
        print("  Brokerage:", out["brokerage_analysis"])

        # HMA Exit Analysis
        hma = out["hma_exit_analysis"]
        if hma.get("available"):
            print(f"\n--- V6.9 HMA Exit System ---")
            print(f"  HMA Trail Activated: {hma['hma_trail_activated']} ({hma['hma_trail_pct']}%)")
            print(f"  BE Armed (T1 hit): {hma['be_armed_count']} ({hma['be_armed_pct']}%)")
            print(f"  Partial Profit Takes: {hma['partial_profit_takes']}")
            print(f"  Bars in Trade: {hma['bars_in_trade_summary']}")
            self._print_table(
                "Exit Reason Analysis (V6.9)",
                hma.get("exit_reason_analysis", []),
                [("exit_reason", "ExitReason"), ("trades", "Trades"), ("win_rate_pct", "WinR%"),
                 ("net_pnl", "NetPnL"), ("avg_pnl", "AvgPnL"), ("avg_bars_in_trade", "AvgBars"),
                 ("avg_mfe_r", "AvgMFE"), ("avg_mae_r", "AvgMAE")],
                max_rows=top,
            )

        # Quality Gates
        gs = qg.get("gate_rejection_stats", {})
        print(f"\n--- V6.7 Quality Gate Rejections (Total: {gs.get('total_gate_rejections', 0)}) ---")
        for k in ("gate_slope_blocked", "gate_freshness_blocked", "gate_price_align_blocked",
                   "gate_separation_blocked", "gate_divergence_blocked"):
            print(f"  {k}: {gs.get(k, 0)}")

        print("\n  Blockers:", out["blocker_analysis"])
        print("  Daily:", out["daily_performance"])

        self._print_table(
            "Direction Matrix (Index × Sector × Signal)",
            out["direction_matrix_index_sector_signal"].get("rows", []),
            [("index_dir", "Index"), ("sector_dir", "Sector"), ("signal_dir", "Signal"),
             ("trades", "Trades"), ("win_rate_pct", "WinR%"), ("net_pnl", "NetPnL")],
        )

        print("\nRisk/Target Summary:")
        rta = out["risk_target_analysis"]
        if rta.get("available"):
            print(f"  Stop %: {rta['summary_stop_pct']}")
            print(f"  Target %: {rta['summary_target_pct']}")
            print(f"  MFE R: {rta['summary_mfe_r']}")
            print(f"  MAE R: {rta['summary_mae_r']}")
            self._print_table(
                "R by Exit Reason",
                rta.get("by_exit_reason", []),
                [("exit_reason", "ExitReason"), ("trades", "Trades"), ("avg_realized_r", "AvgR"),
                 ("avg_mfe_r", "MFE(R)"), ("avg_mae_r", "MAE(R)")],
                max_rows=top,
            )

        touch = out["target_stop_touch_analysis"]
        print("\nTarget/Stop Touch:")
        if touch.get("available"):
            self._print_table(
                "First Touch Performance",
                touch.get("first_touch_performance", []),
                [("first_touch", "FirstTouch"), ("trades", "Trades"), ("win_rate_pct", "WinR%"), ("pnl", "PnL")],
            )

        print("\nCapital Utilization:", out["capital_utilization"].get("summary", {}))

        first = out["first_trade_effect"]
        print(f"\nFirst trade correlation: {first.get('correlation')}")
        self._print_table(
            "First Trade Effect",
            first.get("rows", []),
            [("first_trade_outcome", "Outcome"), ("days", "Days"), ("day_profit_rate_pct", "DayProfit%"),
             ("avg_day_pnl", "AvgDayPnL"), ("win_rate_pct", "WinR%"), ("net_pnl", "NetPnL")],
        )

        self._print_table(
            "Regime Performance",
            out["regime_performance"].get("rows", []),
            [("regime", "Regime"), ("trades", "Trades"), ("win_rate_pct", "WinR%"), ("pnl", "PnL")],
            max_rows=top,
        )

        self._print_table(
            "Time Bucket Performance",
            out["time_bucket_performance"].get("rows", []),
            [("bucket", "Bucket"), ("trades", "Trades"), ("win_rate_pct", "WinR%"), ("pnl", "PnL")],
            max_rows=top,
        )

        self._print_table(
            "Sector Performance",
            out["sector_performance"].get("rows", []),
            [("sector", "Sector"), ("trades", "Trades"), ("win_rate_pct", "WinR%"),
             ("net_pnl", "NetPnL"), ("avg_bars", "AvgBars")],
            max_rows=top,
        )

        sp = out["symbol_performance"]
        self._print_table("Top 10 Winning Symbols", sp.get("top_winners", []),
                          [("symbol", "Symbol"), ("trades", "Trades"), ("win_rate", "WinR%"), ("net_pnl", "NetPnL")])
        self._print_table("Top 10 Losing Symbols", sp.get("top_losers", []),
                          [("symbol", "Symbol"), ("trades", "Trades"), ("win_rate", "WinR%"), ("net_pnl", "NetPnL")])

        print("\n" + line + "\n")
        return out

    @staticmethod
    def export_json(analysis: Dict[str, Any], output_path: str) -> str:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        return output_path


def _find_latest_history_file() -> Optional[Path]:
    root = Path(__file__).parent.parent
    candidates: List[Path] = []
    for folder in ["history_v6.9", "history_v6.8", "history_v6.7", "history"]:
        history_dir = root / folder
        if not history_dir.exists():
            continue
        candidates.extend(history_dir.glob("backtest_history_*.json"))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V6.9 Advanced backtest analysis (HMA exit system)")
    parser.add_argument("history_file", nargs="?", help="History JSON file")
    parser.add_argument("--latest", action="store_true", help="Use latest history file")
    parser.add_argument("--export", action="store_true", help="Export analysis JSON")
    parser.add_argument("--no-market-data", action="store_true", help="Disable market-data analysis")
    parser.add_argument("--top", type=int, default=10, help="Rows for top tables")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    history_file: Optional[Path] = None
    if args.latest:
        history_file = _find_latest_history_file()
        if history_file:
            print(f"Using latest history file: {history_file.name}")
    elif args.history_file:
        history_file = Path(args.history_file)
    else:
        history_file = _find_latest_history_file()

    if not history_file:
        print("Error: no history file found.", file=sys.stderr)
        return 1

    try:
        analyzer = AdvancedBacktestAnalyzerV3(str(history_file), use_market_data=not args.no_market_data)
        analysis = analyzer.print_report(top=max(1, int(args.top)))

        if args.export:
            analysis_dir = Path(__file__).resolve().parent
            dt_match = re.search(
                r"backtest_history_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}_(?:am|pm))",
                history_file.name, re.IGNORECASE,
            )
            if dt_match:
                export_name = f"advanced_analysis_v3_{dt_match.group(1)}.json"
            else:
                stamp = datetime.now()
                export_name = f"advanced_analysis_v3_{stamp.strftime('%d-%m-%Y_%I-%M_%p').lower()}.json"
            export_path = analysis_dir / export_name
            out = AdvancedBacktestAnalyzerV3.export_json(analysis, str(export_path))
            print(f"Analysis exported to: {out}")

        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
