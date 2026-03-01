"""
V6.9 PRO Graph-Based Backtest Analyzer  (v3)
==============================================
Updated for V6.9 sector engine: HMA-based dynamic exit system, signal quality
gates, brokerage decomposition, and new trade/signal fields.

NEW in V3 (V6.9-aware):
  - HMA Exit System section: exit reason decomposition, HMA trail analysis,
    bars-in-trade distributions, partial profit tracking
  - Signal Quality Gates section: gate pass/fail funnel, HMA quality metrics
    (slope, separation, freshness, divergence)
  - Updated PARAM_KEYS for V6.6-V6.9 config snapshot keys
  - Updated data loader for all_trade_records, HMA quality nested dict,
    new trade fields (hma_trail_active, bars_in_trade, last_hma_fast/slow)
  - Removed RVOL/STOCH_RSI/SPREAD_QUALITY scoring (dropped in V6.6+)
  - Default history source: history_v6.9

Usage
-----
    python analyze_backtest_graphs_v3.py
    python analyze_backtest_graphs_v3.py file1.json file2.json --labels Run_A Run_B
    python analyze_backtest_graphs_v3.py --output dashboard.html
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError as exc:
    raise SystemExit(
        "plotly is required.  Install with:  pip install plotly"
    ) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG: Default history sources (edit as needed)
# ═══════════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_SOURCES: List[Dict[str, Any]] = [
    {"path": ROOT / "history_v6.9" / "backtest_history_28-02-2026_06-04_pm.json", "label": "HMA_9_63_2025"},
    {"path": ROOT / "history_v6.9" / "backtest_history_28-02-2026_06-08_pm.json", "label": "HMA_18_126_2025"},
    {"path": ROOT / "history_v6.9" / "backtest_history_28-02-2026_07-00_pm.json", "label": "HMA_18_126_2024"},
    {"path": ROOT / "history_v6.9" / "backtest_history_28-02-2026_07-24_pm.json", "label": "HMA_18_126_2023"},
]

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

_PLOTLY_TEMPLATE = "plotly_white"
_COLOR_WIN = "#22c55e"
_COLOR_LOSS = "#ef4444"
_COLOR_NEUTRAL = "#64748b"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return default if v is None else float(v)
    except (TypeError, ValueError):
        return default


def _pct(n: float, d: float) -> float:
    return (n / d * 100.0) if d else 0.0


def _norm_reason(text: Any) -> str:
    s = str(text or "NA")
    return s.split("(", 1)[0].strip() if "(" in s else s


def _safe_label(path: Path) -> str:
    m = re.search(
        r"backtest_history_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}_(?:am|pm))",
        path.name, re.IGNORECASE,
    )
    return m.group(1) if m else path.stem


# ═══════════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RunBundle:
    label: str
    path: Path
    raw: Dict[str, Any]
    summary: Dict[str, Any]
    config: Dict[str, Any]
    daily: pd.DataFrame
    trades: pd.DataFrame
    signals: pd.DataFrame
    positions: pd.DataFrame
    merged: pd.DataFrame = field(default_factory=pd.DataFrame)


# V6.9-updated parameter keys for config snapshot
PARAM_KEYS = [
    "BASE_RISK_PER_TRADE_PCT", "MAX_CONCURRENT_POSITIONS",
    "MAX_POSITIONS_PER_SECTOR", "MAX_POSITIONS_PER_STOCK",
    "RISK_MULT_LUNCH", "RISK_MULT_WARNING",
    "MIN_ADV_CRORES", "SPREAD_ATR_LIMIT",
    # V6.6 HMA params
    "V6_6_HMA_FAST", "V6_6_HMA_SLOW", "V6_6_SECTOR_RANK_MAX",
    # V6.7 Quality gate params
    "V6_7_SLOPE_LOOKBACK", "V6_7_SLOPE_MIN_PCT",
    "V6_7_CROSS_FRESHNESS_BARS", "V6_7_MIN_HMA_SEP_ATR_FRAC",
    "V6_7_DIVERGENCE_LOOKBACK",
    # V6.8 Brokerage params
    "V6_8_BROKERAGE_PCT", "V6_8_STT_SELL_PCT",
    "V6_8_TRANSACTION_CHARGE_PCT", "V6_8_STAMP_BUY_PCT", "V6_8_GST_PCT",
    # V6.9 Exit system params
    "V6_9_STOP_ATR_MULT_5M", "V6_9_STOP_MIN_PCT",
    "V6_9_HMA_TRAIL_BUFFER_ATR", "V6_9_TARGET_1_R", "V6_9_TARGET_1_EXIT_PCT",
    # VIX
    "VIX_MULT_LOW", "VIX_MULT_NORMAL", "VIX_MULT_ELEVATED",
    "VIX_MULT_HIGH", "VIX_MULT_EXTREME",
    # Sector weights
    "SECTOR_WEIGHTS.structural", "SECTOR_WEIGHTS.shortterm",
    "SECTOR_WEIGHTS.intraday", "SECTOR_WEIGHTS.breadth",
    "SECTOR_WEIGHTS.nifty",
]


def _extract_param(cfg: Dict[str, Any], key: str) -> Optional[float]:
    if "." in key:
        base, sub = key.split(".", 1)
        val = (cfg.get(base) or {}).get(sub)
    else:
        val = cfg.get(key)
    try:
        return None if val is None else float(val)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Loader (V6.9-aware)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_bundle(path: Path, label: str) -> RunBundle:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    run_meta = data.get("run", {})
    summary = data.get("summary", {})
    config = data.get("config_snapshot", {})

    # --- daily ---
    daily = pd.DataFrame(data.get("daily_results", []))
    if not daily.empty:
        daily["day"] = pd.to_datetime(daily["day"], errors="coerce")
        for c in ("pnl", "start_equity", "end_equity"):
            if c in daily.columns:
                daily[c] = pd.to_numeric(daily[c], errors="coerce").fillna(0.0)
        daily = daily.sort_values("day").reset_index(drop=True)
        init_eq = (
            float(daily["start_equity"].dropna().iloc[0])
            if daily["start_equity"].notna().any()
            else _f(summary.get("initial_equity", 1_000_000))
        )
        daily["equity"] = init_eq + daily["pnl"].cumsum()
        daily["peak"] = daily["equity"].cummax()
        daily["dd"] = daily["equity"] - daily["peak"]
        daily["dd_pct"] = np.where(daily["peak"] > 0, (daily["equity"] / daily["peak"] - 1) * 100, 0)
        daily["month"] = daily["day"].dt.to_period("M").astype(str)
        daily["week"] = daily["day"].dt.isocalendar().week.astype(int)
        daily["dow"] = daily["day"].dt.day_name()
        daily["dom"] = daily["day"].dt.day
        daily["trades_count"] = daily.get("trades", pd.Series(0, index=daily.index))
        daily["label"] = label

    # --- trades ---
    trades = pd.DataFrame(data.get("trade_records", []))
    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades.get("entry_time"), errors="coerce")
        trades["exit_time"] = pd.to_datetime(trades.get("exit_time"), errors="coerce")
        for c in ("realized_pnl", "gross_pnl", "entry_price", "notional_at_entry",
                   "total_turnover", "total_charges",
                   "entry_risk_per_share", "entry_atr_5m",
                   "mfe_r", "mae_r",
                   "last_hma_fast", "last_hma_slow"):
            if c in trades.columns:
                trades[c] = pd.to_numeric(trades[c], errors="coerce")
        # V6.9 fields
        if "bars_in_trade" in trades.columns:
            trades["bars_in_trade"] = pd.to_numeric(trades["bars_in_trade"], errors="coerce").fillna(0).astype(int)
        else:
            trades["bars_in_trade"] = 0
        if "hma_trail_active" not in trades.columns:
            trades["hma_trail_active"] = False
        if "be_armed" not in trades.columns:
            trades["be_armed"] = False

        # Brokerage breakdown
        if "brokerage_breakdown" in trades.columns:
            breakdown = pd.json_normalize(trades["brokerage_breakdown"]).add_prefix("charge_")
            if not breakdown.empty:
                trades = pd.concat([trades.drop(columns=["brokerage_breakdown"]), breakdown], axis=1)
        for c in ("charge_brokerage", "charge_stt", "charge_transaction_charge",
                   "charge_sebi_charge", "charge_stamp_charge", "charge_gst"):
            if c not in trades.columns:
                trades[c] = 0.0
            trades[c] = pd.to_numeric(trades[c], errors="coerce").fillna(0.0)

        if "gross_pnl" not in trades.columns:
            trades["gross_pnl"] = trades["realized_pnl"]
        else:
            trades["gross_pnl"] = pd.to_numeric(trades["gross_pnl"], errors="coerce").fillna(trades["realized_pnl"])
        if "total_turnover" not in trades.columns:
            trades["total_turnover"] = 0.0
        if "total_charges" not in trades.columns:
            trades["total_charges"] = 0.0
        trades["total_turnover"] = pd.to_numeric(trades["total_turnover"], errors="coerce").fillna(0.0)
        trades["total_charges"] = pd.to_numeric(trades["total_charges"], errors="coerce").fillna(0.0)
        trades["initial_qty"] = pd.to_numeric(trades.get("initial_qty"), errors="coerce").fillna(0).astype(int)
        if "notional_at_entry" not in trades.columns or trades["notional_at_entry"].isna().all():
            trades["notional_at_entry"] = trades["entry_price"] * trades["initial_qty"]
        trades["duration_min"] = (trades["exit_time"] - trades["entry_time"]).dt.total_seconds() / 60
        trades["entry_hour"] = trades["entry_time"].dt.hour
        trades["entry_minute"] = trades["entry_time"].dt.minute
        trades["entry_hhmm"] = trades["entry_time"].dt.strftime("%H:%M")
        trades["entry_day"] = trades["entry_time"].dt.date
        trades["win"] = trades["realized_pnl"] > 0
        if "entry_risk_per_share" in trades.columns:
            total_risk = trades["entry_risk_per_share"] * trades["initial_qty"]
            trades["r_multiple"] = np.where(total_risk.abs() > 0, trades["realized_pnl"] / total_risk.abs(), 0)
        trades["entry_bucket"] = pd.cut(
            trades["entry_hour"].fillna(-1),
            bins=[-1, 10, 12, 13, 14, 16],
            labels=["OPEN 09:15-10:30", "MID 10:30-12:00", "LUNCH 12:00-13:15",
                     "AFTERNOON 13:15-14:05", "LATE 14:05+"],
            include_lowest=True,
        ).astype(str)
        trades["label"] = label

    # --- signals (V6.9 uses signal_records for executed only) ---
    signal_source = data.get("signal_records", [])
    signals = pd.DataFrame(signal_source)
    if not signals.empty:
        signals["label"] = label
        signals["timestamp"] = pd.to_datetime(signals.get("timestamp"), errors="coerce")
        signals["day"] = signals["timestamp"].dt.date
        for c in ("score", "vix_percentile", "nifty_pct",
                   "change_pct", "adv_crores", "atr", "atr_5m", "price",
                   "hma_fast_5m", "hma_slow_5m",
                   "vix_ltp", "vix_multiplier", "nifty_ltp"):
            if c in signals.columns:
                signals[c] = pd.to_numeric(signals[c], errors="coerce")
        if "sector_rank" in signals.columns:
            signals["sector_rank"] = pd.to_numeric(signals["sector_rank"], errors="coerce")
        # Extract HMA quality
        if "hma_quality" in signals.columns:
            hq = pd.json_normalize(signals["hma_quality"].apply(
                lambda x: x if isinstance(x, dict) else {}
            )).add_prefix("hq_")
            if not hq.empty:
                signals = pd.concat([signals.drop(columns=["hma_quality"]), hq], axis=1)

    # --- all_trade_records (V6.9: includes both executed + non-executed) ---
    all_trades = pd.DataFrame(data.get("all_trade_records", []))

    # --- positions ---
    position_source = data.get("position_records", [])
    positions = pd.DataFrame(position_source)
    if not positions.empty:
        positions["label"] = label
        for c in ("entry_price", "atr", "atr_5m", "stop_price", "target_1", "sizing_shares",
                   "risk_amount", "risk_per_share", "effective_risk_pct", "notional"):
            if c in positions.columns:
                positions[c] = pd.to_numeric(positions[c], errors="coerce")
        # Extract HMA quality from positions too
        if "hma_quality" in positions.columns:
            hq_p = pd.json_normalize(positions["hma_quality"].apply(
                lambda x: x if isinstance(x, dict) else {}
            )).add_prefix("hq_")
            if not hq_p.empty:
                positions = pd.concat([positions.drop(columns=["hma_quality"]), hq_p], axis=1)

    # --- merge trades + signals for enriched analysis ---
    merged = pd.DataFrame()
    if not trades.empty and not signals.empty and "executed_trade_id" in signals.columns:
        executed = signals[signals["executed_trade"] == True].copy()
        if not executed.empty:
            sig_cols = ["executed_trade_id", "regime", "score", "grade",
                        "sector_rank", "vix_ltp", "vix_percentile",
                        "nifty_pct", "change_pct", "hma_align",
                        "adv_crores", "atr", "atr_5m", "vix_multiplier", "nifty_ltp",
                        "hma_fast_5m", "hma_slow_5m",
                        "gate_passed", "gate_reason"]
            # Include HMA quality columns if present
            for c in executed.columns:
                if c.startswith("hq_") and c not in sig_cols:
                    sig_cols.append(c)
            sig_cols = [c for c in sig_cols if c in executed.columns]
            sig_lookup = executed[sig_cols].drop_duplicates("executed_trade_id")
            merged = trades.merge(
                sig_lookup, left_on="trade_id", right_on="executed_trade_id", how="left",
                suffixes=("", "_sig"),
            )
    if merged.empty:
        merged = trades.copy()

    # Direction columns
    if not merged.empty:
        if "nifty_pct" in merged.columns:
            merged["index_dir"] = np.where(merged["nifty_pct"] > 0, "UP", "DOWN")
        elif "index_direction" in merged.columns:
            merged["index_dir"] = merged["index_direction"].apply(
                lambda x: "UP" if str(x).upper() in ("UP", "LONG") else "DOWN" if str(x).upper() in ("DOWN", "SHORT") else "UNKNOWN"
            )
        if "direction" in merged.columns:
            merged["signal_dir"] = np.where(merged["direction"] == "LONG", "UP", "DOWN")

    # Sector direction
    if not merged.empty and not signals.empty and "change_pct" in signals.columns:
        sector_day_dir = (
            signals.groupby(["day", "sector"])["change_pct"]
            .median()
            .reset_index()
            .rename(columns={"change_pct": "_sector_median_chg"})
        )
        sector_day_dir["sector_dir"] = np.where(sector_day_dir["_sector_median_chg"] > 0, "UP", "DOWN")
        merged["_trade_day"] = merged["entry_time"].dt.date
        merged = merged.merge(
            sector_day_dir[["day", "sector", "sector_dir"]],
            left_on=["_trade_day", "sector"], right_on=["day", "sector"], how="left",
        )
        merged.drop(columns=["day_y", "_trade_day"], errors="ignore", inplace=True)
        merged.rename(columns={"day_x": "day"}, errors="ignore", inplace=True)
    elif not merged.empty and "sector_bias_at_entry" in merged.columns:
        merged["sector_dir"] = merged["sector_bias_at_entry"].apply(
            lambda x: "UP" if str(x).upper() in ("BULLISH", "UP") else "DOWN" if str(x).upper() in ("BEARISH", "DOWN") else "UNKNOWN"
        )

    # --- summary row ---
    wins = int((trades["realized_pnl"] > 0).sum()) if not trades.empty else 0
    losses = int((trades["realized_pnl"] < 0).sum()) if not trades.empty else 0
    gp = float(trades.loc[trades["realized_pnl"] > 0, "realized_pnl"].sum()) if not trades.empty else 0
    gl = float(trades.loc[trades["realized_pnl"] < 0, "realized_pnl"].sum()) if not trades.empty else 0
    pf = (gp / abs(gl)) if gl < 0 else float("nan")
    all_signals = int(_f(summary.get("all_a_grade_signals", 0)))
    if all_signals <= 0:
        all_signals = len(all_trades) if not all_trades.empty else len(signals)
    executed_signals = int(_f(summary.get("executed_positions", 0)))
    if executed_signals <= 0:
        executed_signals = len(trades)

    exchange = (
        summary.get("exchange")
        or data.get("inputs", {}).get("exchange")
        or config.get("V6_8_EXCHANGE")
        or "UNKNOWN"
    )
    total_turnover = _f(summary.get("total_turnover", 0.0))
    if total_turnover <= 0 and not trades.empty:
        total_turnover = float(trades["total_turnover"].sum())
    total_charges = _f(summary.get("total_charges", 0.0))
    if total_charges <= 0 and not trades.empty:
        total_charges = float(trades["total_charges"].sum())
    charge_breakdown = summary.get("brokerage_breakdown") or {}
    charge_brokerage = _f(charge_breakdown.get("brokerage", float(trades["charge_brokerage"].sum()) if not trades.empty and "charge_brokerage" in trades.columns else 0.0))
    charge_stt = _f(charge_breakdown.get("stt", float(trades["charge_stt"].sum()) if not trades.empty and "charge_stt" in trades.columns else 0.0))
    charge_transaction = _f(charge_breakdown.get("transaction_charge", float(trades["charge_transaction_charge"].sum()) if not trades.empty and "charge_transaction_charge" in trades.columns else 0.0))
    charge_sebi = _f(charge_breakdown.get("sebi_charge", float(trades["charge_sebi_charge"].sum()) if not trades.empty and "charge_sebi_charge" in trades.columns else 0.0))
    charge_stamp = _f(charge_breakdown.get("stamp_charge", float(trades["charge_stamp_charge"].sum()) if not trades.empty and "charge_stamp_charge" in trades.columns else 0.0))
    charge_gst = _f(charge_breakdown.get("gst", float(trades["charge_gst"].sum()) if not trades.empty and "charge_gst" in trades.columns else 0.0))
    gross_return = _f(summary.get("gross_return_before_charges", _f(summary.get("total_return", 0.0)) + total_charges))

    # HMA config for summary row
    hma_fast = config.get("V6_6_HMA_FAST", "?")
    hma_slow = config.get("V6_6_HMA_SLOW", "?")
    freshness_bars = config.get("V6_7_CROSS_FRESHNESS_BARS", "?")

    # Gate stats
    gate_slope = int(_f(summary.get("gate_slope_blocked", 0)))
    gate_freshness = int(_f(summary.get("gate_freshness_blocked", 0)))
    gate_price_align = int(_f(summary.get("gate_price_align_blocked", 0)))
    gate_separation = int(_f(summary.get("gate_separation_blocked", 0)))
    gate_divergence = int(_f(summary.get("gate_divergence_blocked", 0)))
    total_gate_blocked = gate_slope + gate_freshness + gate_price_align + gate_separation + gate_divergence

    # HMA exit stats from trades
    hma_trail_count = int(trades["hma_trail_active"].sum()) if not trades.empty and "hma_trail_active" in trades.columns else 0
    be_armed_count = int(trades["be_armed"].sum()) if not trades.empty and "be_armed" in trades.columns else 0

    row: Dict[str, Any] = {
        "label": label, "path": str(path),
        "run_id": run_meta.get("run_id", ""),
        "status": run_meta.get("status", ""),
        "start_date": run_meta.get("start_date", ""),
        "end_date": run_meta.get("end_date", ""),
        "initial_equity": _f(summary.get("initial_equity")),
        "final_equity": _f(summary.get("final_equity")),
        "total_return": _f(summary.get("total_return")),
        "gross_return_before_charges": gross_return,
        "total_return_pct": _f(summary.get("total_return_pct")),
        "trading_days": int(_f(summary.get("trading_days", 0))),
        "closed_trades": int(_f(summary.get("closed_trades", len(trades)))),
        "all_signals": all_signals,
        "executed_signals": executed_signals,
        "wins": wins, "losses": losses,
        "win_rate_pct": round(_pct(wins, max(1, wins + losses)), 2),
        "profit_factor": round(pf, 3) if pd.notna(pf) else float("nan"),
        "avg_trade_pnl": round(float(trades["realized_pnl"].mean()), 2) if not trades.empty else 0,
        "best_trade": float(trades["realized_pnl"].max()) if not trades.empty else 0,
        "worst_trade": float(trades["realized_pnl"].min()) if not trades.empty else 0,
        "gross_profit": gp, "gross_loss": gl,
        "exchange": str(exchange),
        "total_turnover": total_turnover,
        "total_charges": total_charges,
        "charges_pct_turnover": round(_pct(total_charges, total_turnover), 4),
        "charge_brokerage": charge_brokerage,
        "charge_stt": charge_stt,
        "charge_transaction": charge_transaction,
        "charge_sebi": charge_sebi,
        "charge_stamp": charge_stamp,
        "charge_gst": charge_gst,
        "execution_rate_pct": round(_pct(executed_signals, all_signals), 2),
        "blocked_count": int(_f(summary.get("blocked_by_max_positions_count", 0))),
        "decision_counts": summary.get("decision_counts") or {},
        "risk_reason_counts": summary.get("risk_reason_counts") or {},
        # V6.9 HMA config
        "hma_fast": hma_fast,
        "hma_slow": hma_slow,
        "freshness_bars": freshness_bars,
        # V6.9 HMA exit stats
        "hma_trail_count": hma_trail_count,
        "be_armed_count": be_armed_count,
        # Gate stats
        "total_gate_blocked": total_gate_blocked,
        "gate_slope_blocked": gate_slope,
        "gate_freshness_blocked": gate_freshness,
        "gate_price_align_blocked": gate_price_align,
        "gate_separation_blocked": gate_separation,
        "gate_divergence_blocked": gate_divergence,
    }
    if not daily.empty:
        row["max_dd_inr"] = float((-daily["dd"]).max())
        row["max_dd_pct"] = float((-daily["dd_pct"]).max())
        row["avg_daily_pnl"] = float(daily["pnl"].mean())
        row["positive_days"] = int((daily["pnl"] > 0).sum())
        row["negative_days"] = int((daily["pnl"] < 0).sum())
        std = daily["pnl"].std()
        row["sharpe_daily"] = round((daily["pnl"].mean() / std) * math.sqrt(252), 2) if std > 0 else 0
    if not trades.empty and "r_multiple" in trades.columns:
        row["avg_r"] = round(float(trades["r_multiple"].mean()), 3)
        row["expectancy_r"] = round(float(trades["r_multiple"].mean()), 3)
    if not trades.empty and "bars_in_trade" in trades.columns:
        row["avg_bars_in_trade"] = round(float(trades["bars_in_trade"].mean()), 1)
    for k in PARAM_KEYS:
        row[k] = _extract_param(config, k)

    return RunBundle(label=label, path=path, raw=data, summary=row,
                     config=config, daily=daily, trades=trades,
                     signals=signals, positions=positions, merged=merged)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class ProGraphAnalyzerV3:

    SECTIONS = [
        ("summary",    "1. Executive Summary"),
        ("equity",     "2. Equity & Drawdown Journey"),
        ("hma_exit",   "3. HMA Exit System Analysis"),
        ("quality",    "4. Signal Quality Gates & HMA Metrics"),
        ("calendar",   "5. Calendar & Temporal Patterns"),
        ("direction",  "6. Direction Alignment Matrix"),
        ("trades",     "7. Trade Deep Dive"),
        ("regime",     "8. Regime & VIX Analysis"),
        ("timing",     "9. Intraday Timing Patterns"),
        ("sectors",    "10. Sector Analysis"),
        ("funnel",     "11. Execution Funnel"),
        ("risk",       "12. Risk & Position Sizing"),
        ("params",     "13. Parameter Optimization"),
    ]

    def __init__(self, files: Sequence[Path], labels: Optional[Sequence[str]] = None):
        self.files = list(files)
        self.labels = list(labels) if labels else []
        self.bundles: List[RunBundle] = []

    def load(self) -> None:
        self.bundles.clear()
        for i, fp in enumerate(self.files):
            lbl = self.labels[i] if i < len(self.labels) else _safe_label(fp)
            self.bundles.append(_load_bundle(fp, lbl))
        print(f"  Loaded {len(self.bundles)} runs")

    @property
    def summary_df(self) -> pd.DataFrame:
        return pd.DataFrame([b.summary for b in self.bundles])

    def _cat(self, attr: str) -> pd.DataFrame:
        frames = [getattr(b, attr) for b in self.bundles if not getattr(b, attr).empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def _fig_html(fig: go.Figure, js: bool = False) -> str:
        fig.update_layout(template=_PLOTLY_TEMPLATE, legend_title_text="",
                          margin=dict(l=60, r=30, t=50, b=50))
        return fig.to_html(full_html=False,
                           include_plotlyjs=("cdn" if js else False),
                           config={"displaylogo": False})

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION BUILDERS
    # ══════════════════════════════════════════════════════════════════════════

    # ---- 1. Executive Summary ------------------------------------------------

    def _section_summary(self, js: bool) -> Tuple[str, List[str]]:
        sdf = self.summary_df
        blocks: List[str] = []

        cols = [
            ("label", "Run"), ("start_date", "Start"), ("end_date", "End"),
            ("trading_days", "Days"), ("closed_trades", "Trades"),
            ("hma_fast", "HMA_F"), ("hma_slow", "HMA_S"), ("freshness_bars", "Fresh"),
            ("win_rate_pct", "Win %"), ("profit_factor", "PF"),
            ("total_return_pct", "Return %"), ("max_dd_pct", "Max DD %"),
            ("avg_trade_pnl", "Avg PnL"), ("execution_rate_pct", "Exec %"),
            ("total_charges", "Charges"), ("charges_pct_turnover", "Chg% TO"),
            ("sharpe_daily", "Sharpe"), ("avg_r", "Avg R"),
            ("avg_bars_in_trade", "Avg Bars"),
        ]
        avail = [(k, n) for k, n in cols if k in sdf.columns]
        header = "".join(f"<th>{n}</th>" for _, n in avail)
        rows_html = ""
        for _, r in sdf.iterrows():
            cells = "".join(
                f"<td>{r.get(k, '')}</td>" if isinstance(r.get(k), str)
                else f"<td>{r.get(k, ''):.2f}</td>" if isinstance(r.get(k), float)
                else f"<td>{r.get(k, '')}</td>"
                for k, _ in avail
            )
            rows_html += f"<tr>{cells}</tr>"
        blocks.append(f"""
        <div style="overflow-x:auto;">
        <table class="score-table"><thead><tr>{header}</tr></thead>
        <tbody>{rows_html}</tbody></table></div>""")

        # Radar chart
        radar_metrics = ["win_rate_pct", "profit_factor", "execution_rate_pct", "total_return_pct"]
        radar_names = ["Win Rate %", "Profit Factor", "Execution Rate %", "Return %"]
        if "sharpe_daily" in sdf.columns:
            radar_metrics.append("sharpe_daily")
            radar_names.append("Sharpe (ann.)")
        fig = go.Figure()
        for _, r in sdf.iterrows():
            vals = [_f(r.get(m)) for m in radar_metrics]
            fig.add_trace(go.Scatterpolar(
                r=vals + [vals[0]], theta=radar_names + [radar_names[0]],
                name=r["label"], fill="toself", opacity=0.6,
            ))
        fig.update_layout(title="Multi-Metric Radar Comparison",
                          polar=dict(radialaxis=dict(visible=True)))
        blocks.append(self._fig_html(fig, js=js))

        # Charges bar
        if "total_charges" in sdf.columns:
            fig_cost = px.bar(
                sdf.sort_values("total_charges", ascending=False),
                x="label", y="total_charges", color="label",
                title="Total Brokerage/Statutory Charges by Run", text_auto=".2s",
            )
            fig_cost.update_layout(showlegend=False, yaxis_title="Charges (INR)", height=360)
            blocks.append(self._fig_html(fig_cost))

        # Charge breakdown stacked
        charge_cols = [
            ("charge_brokerage", "Brokerage"), ("charge_stt", "STT/CTT"),
            ("charge_transaction", "Transaction"), ("charge_sebi", "SEBI"),
            ("charge_stamp", "Stamp"), ("charge_gst", "GST"),
        ]
        if all(c in sdf.columns for c, _ in charge_cols):
            rows_data = []
            for _, r in sdf.iterrows():
                for c, name in charge_cols:
                    rows_data.append({"label": r["label"], "component": name, "value": _f(r.get(c))})
            cdf = pd.DataFrame(rows_data)
            fig_break = px.bar(cdf, x="label", y="value", color="component", barmode="stack",
                               title="Charge Component Breakdown by Run")
            fig_break.update_layout(yaxis_title="Charges (INR)", height=380)
            blocks.append(self._fig_html(fig_break))

        # Gross vs Net return comparison
        if "gross_return_before_charges" in sdf.columns:
            ret_data = []
            for _, r in sdf.iterrows():
                ret_data.append({"label": r["label"], "type": "Gross Return", "value": _f(r.get("gross_return_before_charges"))})
                ret_data.append({"label": r["label"], "type": "Net Return", "value": _f(r.get("total_return"))})
                ret_data.append({"label": r["label"], "type": "Charges", "value": -_f(r.get("total_charges"))})
            fig_ret = px.bar(pd.DataFrame(ret_data), x="label", y="value", color="type",
                             barmode="group", title="Gross vs Net Return vs Charges")
            fig_ret.update_layout(yaxis_title="INR", height=400)
            blocks.append(self._fig_html(fig_ret))

        return "summary", blocks

    # ---- 2. Equity & Drawdown ------------------------------------------------

    def _section_equity(self, js: bool) -> Tuple[str, List[str]]:
        daily = self._cat("daily")
        blocks: List[str] = []
        if daily.empty:
            return "equity", blocks

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                            vertical_spacing=0.04,
                            subplot_titles=("Equity Curve", "Underwater Drawdown %"))
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl]
            fig.add_trace(go.Scatter(x=d["day"], y=d["equity"], name=lbl, mode="lines"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d["day"], y=d["dd_pct"], name=f"{lbl} DD",
                                     fill="tozeroy", opacity=0.4, showlegend=False), row=2, col=1)
        fig.update_yaxes(title_text="Equity (INR)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown %", row=2, col=1)
        fig.update_layout(title="Equity Curve with Underwater Drawdown", height=600)
        blocks.append(self._fig_html(fig, js=js))

        # Rolling 20-day return
        fig2 = go.Figure()
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl].copy()
            d["rolling_ret"] = d["equity"].pct_change(20) * 100
            fig2.add_trace(go.Scatter(x=d["day"], y=d["rolling_ret"], name=lbl, mode="lines"))
        fig2.update_layout(title="Rolling 20-Day Return %",
                           yaxis_title="Return %", xaxis_title="Date", height=400)
        blocks.append(self._fig_html(fig2))

        # Daily P&L bars
        for b in self.bundles:
            if b.daily.empty:
                continue
            d = b.daily.copy()
            colors = [_COLOR_WIN if v > 0 else _COLOR_LOSS for v in d["pnl"]]
            fig3 = go.Figure(go.Bar(x=d["day"], y=d["pnl"], marker_color=colors, name=b.label))
            fig3.update_layout(title=f"Daily P&L Bars – {b.label}", yaxis_title="P&L (INR)",
                               xaxis_title="Date", height=350)
            blocks.append(self._fig_html(fig3))

        # Cumulative P&L normalized
        fig4 = go.Figure()
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl]
            init = d["equity"].iloc[0] - d["pnl"].iloc[0]
            fig4.add_trace(go.Scatter(
                x=d["day"], y=(d["equity"] / init - 1) * 100,
                name=lbl, mode="lines",
            ))
        fig4.update_layout(title="Cumulative Return % (Normalized)", yaxis_title="Return %", height=400)
        blocks.append(self._fig_html(fig4))

        return "equity", blocks

    # ---- 3. HMA Exit System Analysis (NEW V6.9) -----------------------------

    def _section_hma_exit(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "hma_exit", blocks

        # Exit reason performance breakdown
        exit_perf = trades.groupby(["label", "exit_reason"], as_index=False).agg(
            count=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            avg_bars=("bars_in_trade", "mean"),
        )

        fig = make_subplots(rows=2, cols=2,
                            subplot_titles=("Net P&L by Exit Reason", "Win Rate %",
                                            "Avg P&L per Trade", "Avg Bars in Trade"))
        for lbl in exit_perf["label"].unique():
            sub = exit_perf[exit_perf["label"] == lbl]
            fig.add_trace(go.Bar(x=sub["exit_reason"], y=sub["net_pnl"], name=lbl), row=1, col=1)
            fig.add_trace(go.Bar(x=sub["exit_reason"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig.add_trace(go.Bar(x=sub["exit_reason"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=2, col=1)
            fig.add_trace(go.Bar(x=sub["exit_reason"], y=sub["avg_bars"], name=lbl, showlegend=False), row=2, col=2)
        fig.update_layout(title="V6.9 Exit Reason Analysis", barmode="group", height=650)
        blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Exit reason sunburst per run
        for b in self.bundles:
            if b.trades.empty:
                continue
            sun_data = b.trades.groupby(["direction", "exit_reason"], as_index=False).agg(
                count=("realized_pnl", "size"), net_pnl=("realized_pnl", "sum"),
            )
            fig_sun = px.sunburst(sun_data, path=["direction", "exit_reason"], values="count",
                                   color="net_pnl",
                                   color_continuous_scale=["#ef4444", "#fefce8", "#22c55e"],
                                   color_continuous_midpoint=0,
                                   title=f"Exit Reason Sunburst – {b.label}")
            fig_sun.update_layout(height=500)
            blocks.append(self._fig_html(fig_sun))

        # Bars in trade distribution
        if "bars_in_trade" in trades.columns:
            fig_bars = px.histogram(trades, x="bars_in_trade", color="label", barmode="overlay",
                                     nbins=50, opacity=0.7,
                                     title="Bars in Trade Distribution")
            fig_bars.update_layout(xaxis_title="Bars (5m candles)", yaxis_title="Count", height=400)
            blocks.append(self._fig_html(fig_bars))

            # Bars in trade by exit reason
            fig_bars_exit = px.box(trades, x="exit_reason", y="bars_in_trade", color="label",
                                    title="Bars in Trade by Exit Reason")
            fig_bars_exit.update_layout(height=400, xaxis_tickangle=25)
            blocks.append(self._fig_html(fig_bars_exit))

        # HMA trail activation rate
        trail_data = []
        for b in self.bundles:
            if b.trades.empty or "hma_trail_active" not in b.trades.columns:
                continue
            total = len(b.trades)
            trail = int(b.trades["hma_trail_active"].sum())
            be = int(b.trades["be_armed"].sum()) if "be_armed" in b.trades.columns else 0
            trail_data.append({"label": b.label, "status": "HMA Trail Active", "count": trail, "pct": round(_pct(trail, total), 1)})
            trail_data.append({"label": b.label, "status": "BE Armed (T1 hit)", "count": be, "pct": round(_pct(be, total), 1)})
            trail_data.append({"label": b.label, "status": "Neither", "count": total - max(trail, be), "pct": round(_pct(total - max(trail, be), total), 1)})
        if trail_data:
            tdf = pd.DataFrame(trail_data)
            fig_trail = px.bar(tdf, x="label", y="count", color="status", barmode="stack",
                                title="HMA Trail & BE Armed Status at Exit",
                                text="pct")
            fig_trail.update_layout(height=400, yaxis_title="Trade Count")
            blocks.append(self._fig_html(fig_trail))

        # Duration vs P&L colored by exit reason
        t = trades.dropna(subset=["duration_min"]).copy()
        if not t.empty:
            fig_dur = px.scatter(t, x="duration_min", y="realized_pnl",
                                  color="exit_reason", symbol="label" if t["label"].nunique() > 1 else None,
                                  opacity=0.4,
                                  title="Trade Duration vs P&L (by Exit Reason)",
                                  hover_data=["symbol", "bars_in_trade"])
            fig_dur.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_dur.update_layout(xaxis_title="Duration (min)", yaxis_title="P&L (INR)", height=500)
            blocks.append(self._fig_html(fig_dur))

        # MFE/MAE by exit reason
        if "mfe_r" in trades.columns and "mae_r" in trades.columns:
            mfe_mae = trades.dropna(subset=["mfe_r", "mae_r"]).copy()
            if not mfe_mae.empty:
                fig_mfe = px.scatter(mfe_mae, x="mae_r", y="mfe_r", color="exit_reason",
                                      symbol="label" if mfe_mae["label"].nunique() > 1 else None,
                                      opacity=0.4,
                                      title="MFE vs MAE by Exit Reason",
                                      hover_data=["symbol", "realized_pnl", "bars_in_trade"])
                fig_mfe.add_shape(type="line", x0=0, y0=0,
                                   x1=mfe_mae["mae_r"].max(), y1=mfe_mae["mae_r"].max(),
                                   line=dict(dash="dash", color="gray"))
                fig_mfe.update_layout(xaxis_title="MAE (R)", yaxis_title="MFE (R)", height=500)
                blocks.append(self._fig_html(fig_mfe))

        return "hma_exit", blocks

    # ---- 4. Signal Quality Gates & HMA Metrics (NEW V6.9) -------------------

    def _section_quality(self, js: bool) -> Tuple[str, List[str]]:
        sdf = self.summary_df
        blocks: List[str] = []

        # Gate rejection breakdown (bar chart per run)
        gate_cols = ["gate_slope_blocked", "gate_freshness_blocked",
                     "gate_price_align_blocked", "gate_separation_blocked",
                     "gate_divergence_blocked"]
        gate_names = ["Slope", "Freshness", "Price Align", "Separation", "Divergence"]
        if all(c in sdf.columns for c in gate_cols):
            rows_data = []
            for _, r in sdf.iterrows():
                for col, name in zip(gate_cols, gate_names):
                    rows_data.append({"label": r["label"], "gate": name, "blocked": int(_f(r.get(col, 0)))})
            gdf = pd.DataFrame(rows_data)
            fig = px.bar(gdf, x="gate", y="blocked", color="label", barmode="group",
                          title="Quality Gate Rejections by Type", text_auto=True)
            fig.update_layout(yaxis_title="Signals Blocked", height=400)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Gate funnel (total signals → gate passed → executed)
        for b in self.bundles:
            s = b.summary
            total_sigs = int(s.get("all_signals", 0))
            gate_blocked = int(s.get("total_gate_blocked", 0))
            gate_passed = total_sigs - gate_blocked
            blocked_positions = int(s.get("blocked_count", 0))
            executed = int(s.get("executed_signals", 0))
            wins = int(s.get("wins", 0))

            stages = ["All A+ Signals", "Gate Passed", "Executed", "Profitable"]
            values = [total_sigs, gate_passed, executed, wins]

            fig_f = go.Figure(go.Funnel(
                y=stages, x=values,
                textposition="inside",
                textinfo="value+percent initial",
                marker=dict(color=["#3b82f6", "#8b5cf6", "#22c55e", "#10b981"]),
            ))
            fig_f.update_layout(title=f"Signal Quality Funnel – {b.label}", height=400)
            blocks.append(self._fig_html(fig_f))

        # HMA quality metrics on executed trades (from signals)
        signals = self._cat("signals")
        if not signals.empty:
            hq_cols = {
                "hq_slope_fast": "HMA Fast Slope",
                "hq_slope_slow": "HMA Slow Slope",
                "hq_cross_bars_ago": "Cross Bars Ago",
                "hq_separation": "HMA Separation",
                "hq_sep_atr_frac": "Separation / ATR",
            }
            for col, name in hq_cols.items():
                if col in signals.columns:
                    s = signals.dropna(subset=[col])
                    if not s.empty:
                        fig_hq = px.histogram(s, x=col, color="label", barmode="overlay",
                                               nbins=40, opacity=0.7,
                                               title=f"HMA Quality: {name} Distribution")
                        fig_hq.update_layout(xaxis_title=name, height=350)
                        blocks.append(self._fig_html(fig_hq))

            # Divergence flag: diverging vs converging PnL
            merged = self._cat("merged")
            if not merged.empty and "hq_is_diverging" in merged.columns:
                div_perf = merged.groupby(["label", "hq_is_diverging"], as_index=False).agg(
                    trades=("realized_pnl", "size"),
                    net_pnl=("realized_pnl", "sum"),
                    avg_pnl=("realized_pnl", "mean"),
                    win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                )
                div_perf["divergence"] = np.where(div_perf["hq_is_diverging"], "Diverging", "Converging")
                fig_div = make_subplots(rows=1, cols=3,
                                         subplot_titles=("Net P&L", "Avg P&L", "Win Rate %"))
                for lbl in div_perf["label"].unique():
                    sub = div_perf[div_perf["label"] == lbl]
                    fig_div.add_trace(go.Bar(x=sub["divergence"], y=sub["net_pnl"], name=lbl), row=1, col=1)
                    fig_div.add_trace(go.Bar(x=sub["divergence"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=1, col=2)
                    fig_div.add_trace(go.Bar(x=sub["divergence"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=3)
                fig_div.update_layout(title="Diverging vs Converging HMA: Performance", barmode="group", height=400)
                blocks.append(self._fig_html(fig_div))

            # Cross bars ago vs PnL scatter
            if "hq_cross_bars_ago" in merged.columns:
                m = merged.dropna(subset=["hq_cross_bars_ago"])
                if not m.empty:
                    fig_cross = px.scatter(m, x="hq_cross_bars_ago", y="realized_pnl",
                                            color="label", opacity=0.3,
                                            title="HMA Cross Freshness (bars ago) vs P&L")
                    fig_cross.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig_cross.update_layout(xaxis_title="Bars Since HMA Cross", yaxis_title="P&L (INR)", height=400)
                    blocks.append(self._fig_html(fig_cross))

            # Separation / ATR vs PnL
            if "hq_sep_atr_frac" in merged.columns:
                m = merged.dropna(subset=["hq_sep_atr_frac"])
                if not m.empty:
                    fig_sep = px.scatter(m, x="hq_sep_atr_frac", y="realized_pnl",
                                          color="label", opacity=0.3,
                                          title="HMA Separation/ATR vs P&L")
                    fig_sep.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig_sep.update_layout(xaxis_title="Separation / ATR", yaxis_title="P&L (INR)", height=400)
                    blocks.append(self._fig_html(fig_sep))

        # HMA config comparison table
        hma_config_cols = [
            ("V6_6_HMA_FAST", "HMA Fast"), ("V6_6_HMA_SLOW", "HMA Slow"),
            ("V6_7_CROSS_FRESHNESS_BARS", "Freshness Bars"),
            ("V6_7_SLOPE_MIN_PCT", "Slope Min %"),
            ("V6_7_MIN_HMA_SEP_ATR_FRAC", "Sep ATR Frac"),
            ("V6_9_STOP_ATR_MULT_5M", "Stop ATR Mult"),
            ("V6_9_HMA_TRAIL_BUFFER_ATR", "Trail Buffer ATR"),
            ("V6_9_TARGET_1_R", "Target 1 R"),
        ]
        avail_cfg = [(k, n) for k, n in hma_config_cols if k in sdf.columns and sdf[k].notna().any()]
        if avail_cfg:
            cfg_rows = []
            for _, r in sdf.iterrows():
                for k, n in avail_cfg:
                    cfg_rows.append({"label": r["label"], "param": n, "value": _f(r.get(k, 0))})
            cfg_df = pd.DataFrame(cfg_rows)
            fig_cfg = px.bar(cfg_df, x="param", y="value", color="label",
                              barmode="group", title="HMA & Exit System Configuration Comparison")
            fig_cfg.update_layout(height=400, xaxis_tickangle=25)
            blocks.append(self._fig_html(fig_cfg))

        return "quality", blocks

    # ---- 5. Calendar & Temporal -----------------------------------------------

    def _section_calendar(self, js: bool) -> Tuple[str, List[str]]:
        daily = self._cat("daily")
        blocks: List[str] = []
        if daily.empty:
            return "calendar", blocks

        for b in self.bundles:
            if b.daily.empty:
                continue
            d = b.daily.copy()
            d["month_str"] = d["day"].dt.strftime("%Y-%m")
            d["dom"] = d["day"].dt.day
            pivot = d.pivot_table(index="month_str", columns="dom", values="pnl", aggfunc="sum")
            pivot = pivot.reindex(columns=range(1, 32))
            fig = go.Figure(go.Heatmap(
                z=pivot.values, x=[str(i) for i in pivot.columns],
                y=pivot.index.tolist(),
                colorscale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                zmid=0, colorbar_title="P&L",
                hovertemplate="Month: %{y}<br>Day: %{x}<br>P&L: ₹%{z:,.0f}<extra></extra>",
            ))
            fig.update_layout(title=f"Calendar Heatmap – {b.label}",
                              xaxis_title="Day of Month", yaxis_title="Month",
                              yaxis_autorange="reversed", height=max(300, len(pivot) * 30 + 100))
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        dow = daily.groupby(["label", "dow"], as_index=False).agg(
            avg_pnl=("pnl", "mean"), total_pnl=("pnl", "sum"),
            win_pct=("pnl", lambda s: _pct((s > 0).sum(), len(s))),
            days=("pnl", "size"),
        )
        dow["dow"] = pd.Categorical(dow["dow"], categories=dow_order, ordered=True)
        dow = dow.sort_values("dow")
        fig2 = make_subplots(rows=1, cols=2, subplot_titles=("Avg Daily P&L by Day of Week",
                                                              "Win Rate % by Day of Week"))
        for lbl in daily["label"].unique():
            sub = dow[dow["label"] == lbl]
            fig2.add_trace(go.Bar(x=sub["dow"], y=sub["avg_pnl"], name=lbl), row=1, col=1)
            fig2.add_trace(go.Bar(x=sub["dow"], y=sub["win_pct"], name=lbl, showlegend=False), row=1, col=2)
        fig2.update_layout(title="Day-of-Week Analysis", barmode="group", height=400)
        blocks.append(self._fig_html(fig2))

        monthly = daily.groupby(["label", "month"], as_index=False)["pnl"].sum()
        if not monthly.empty:
            pivot_m = monthly.pivot_table(index="label", columns="month", values="pnl", aggfunc="sum")
            fig3 = go.Figure(go.Heatmap(
                z=pivot_m.values, x=pivot_m.columns.tolist(), y=pivot_m.index.tolist(),
                colorscale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                zmid=0, colorbar_title="P&L",
                hovertemplate="Run: %{y}<br>Month: %{x}<br>P&L: ₹%{z:,.0f}<extra></extra>",
            ))
            fig3.update_layout(title="Monthly P&L Matrix (Run × Month)", height=max(250, len(pivot_m) * 50 + 100))
            blocks.append(self._fig_html(fig3))

        # Rolling win rate
        fig4 = go.Figure()
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl].copy()
            d["win_flag"] = (d["pnl"] > 0).astype(float)
            d["rolling_wr"] = d["win_flag"].rolling(20, min_periods=5).mean() * 100
            fig4.add_trace(go.Scatter(x=d["day"], y=d["rolling_wr"], name=lbl, mode="lines"))
        fig4.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
        fig4.update_layout(title="Rolling 20-Day Win Rate %", yaxis_title="Win Rate %", height=400)
        blocks.append(self._fig_html(fig4))

        return "calendar", blocks

    # ---- 6. Direction Alignment Matrix ----------------------------------------

    def _section_direction(self, js: bool) -> Tuple[str, List[str]]:
        merged = self._cat("merged")
        blocks: List[str] = []
        if merged.empty or "index_dir" not in merged.columns or "signal_dir" not in merged.columns:
            blocks.append("<p class='muted'>Direction matrix requires signal data.</p>")
            return "direction", blocks

        if "sector_dir" not in merged.columns:
            merged["sector_dir"] = "UNKNOWN"

        m = merged[merged["index_dir"].isin(["UP", "DOWN"]) &
                    merged["sector_dir"].isin(["UP", "DOWN"]) &
                    merged["signal_dir"].isin(["UP", "DOWN"])]
        if m.empty:
            return "direction", blocks

        combos = m.groupby(["label", "index_dir", "sector_dir", "signal_dir"], as_index=False).agg(
            trades=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
        )

        for lbl in combos["label"].unique():
            sub = combos[combos["label"] == lbl]
            idx_order = ["UP", "DOWN"]
            pnl_matrix, wr_matrix, trade_matrix = [], [], []
            y_labels = []
            for id_ in idx_order:
                for sd in idx_order:
                    y_labels.append(f"Idx:{id_} Sec:{sd}")
                    row_pnl, row_wr, row_tr = [], [], []
                    for sig in ["UP", "DOWN"]:
                        match = sub[(sub["index_dir"] == id_) & (sub["sector_dir"] == sd) & (sub["signal_dir"] == sig)]
                        row_pnl.append(float(match["net_pnl"].sum()) if not match.empty else 0)
                        row_wr.append(float(match["win_rate"].mean()) if not match.empty else 0)
                        row_tr.append(int(match["trades"].sum()) if not match.empty else 0)
                    pnl_matrix.append(row_pnl)
                    wr_matrix.append(row_wr)
                    trade_matrix.append(row_tr)

            custom_text = [[f"P&L: ₹{pnl_matrix[i][j]:,.0f}<br>WR: {wr_matrix[i][j]:.1f}%<br>Trades: {trade_matrix[i][j]}"
                            for j in range(2)] for i in range(4)]
            fig = go.Figure(go.Heatmap(
                z=pnl_matrix, x=["Signal: UP (LONG)", "Signal: DOWN (SHORT)"],
                y=y_labels, text=custom_text, texttemplate="%{text}",
                colorscale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                zmid=0, colorbar_title="Net P&L",
            ))
            fig.update_layout(title=f"Direction Alignment Matrix (P&L) – {lbl}", height=400)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Alignment categories
        def _alignment(row):
            aligned = 0
            if row.get("index_dir") == row.get("signal_dir"):
                aligned += 1
            if row.get("sector_dir") == row.get("signal_dir"):
                aligned += 1
            return "Fully Aligned" if aligned == 2 else "Partially Aligned" if aligned == 1 else "Counter-Trend"

        m_copy = m.copy()
        m_copy["alignment"] = m_copy.apply(_alignment, axis=1)
        align_perf = m_copy.groupby(["label", "alignment"], as_index=False).agg(
            trades=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
        )
        fig_align = make_subplots(rows=1, cols=3,
                                   subplot_titles=("Net P&L", "Win Rate %", "Trade Count"))
        for lbl in align_perf["label"].unique():
            sub = align_perf[align_perf["label"] == lbl]
            fig_align.add_trace(go.Bar(x=sub["alignment"], y=sub["net_pnl"], name=lbl), row=1, col=1)
            fig_align.add_trace(go.Bar(x=sub["alignment"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig_align.add_trace(go.Bar(x=sub["alignment"], y=sub["trades"], name=lbl, showlegend=False), row=1, col=3)
        fig_align.update_layout(title="Alignment Category Performance", barmode="group", height=400)
        blocks.append(self._fig_html(fig_align))

        return "direction", blocks

    # ---- 7. Trade Deep Dive --------------------------------------------------

    def _section_trades(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "trades", blocks

        # MFE vs MAE
        if "mfe_r" in trades.columns and "mae_r" in trades.columns:
            t = trades.dropna(subset=["mfe_r", "mae_r"])
            if not t.empty:
                t = t.copy()
                t["outcome"] = np.where(t["realized_pnl"] > 0, "Win", "Loss")
                fig = px.scatter(t, x="mae_r", y="mfe_r", color="outcome",
                                 symbol="label" if t["label"].nunique() > 1 else None,
                                 color_discrete_map={"Win": _COLOR_WIN, "Loss": _COLOR_LOSS},
                                 opacity=0.5,
                                 hover_data=["symbol", "realized_pnl", "exit_reason"],
                                 title="MFE vs MAE (R-Multiples)")
                fig.add_shape(type="line", x0=0, y0=0, x1=t["mae_r"].max(), y1=t["mae_r"].max(),
                              line=dict(dash="dash", color="gray"))
                fig.update_layout(xaxis_title="MAE (R)", yaxis_title="MFE (R)", height=500)
                blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # R-Multiple Distribution
        if "r_multiple" in trades.columns:
            t = trades.dropna(subset=["r_multiple"])
            if not t.empty:
                fig2 = px.histogram(t, x="r_multiple", color="label", barmode="overlay",
                                    nbins=60, opacity=0.7, title="R-Multiple Distribution")
                fig2.add_vline(x=0, line_dash="dash", line_color="black")
                fig2.update_layout(xaxis_title="R-Multiple", yaxis_title="Trade Count", height=400)
                blocks.append(self._fig_html(fig2))

        # Win/Loss P&L violin
        trades_copy = trades.copy()
        trades_copy["outcome"] = np.where(trades_copy["realized_pnl"] > 0, "Win", "Loss")
        fig3 = px.violin(trades_copy, x="label", y="realized_pnl", color="outcome",
                          color_discrete_map={"Win": _COLOR_WIN, "Loss": _COLOR_LOSS},
                          box=True, points=False,
                          title="Win vs Loss P&L Distribution")
        fig3.update_layout(height=450)
        blocks.append(self._fig_html(fig3))

        # Trade duration
        if "duration_min" in trades.columns:
            fig4 = px.histogram(trades, x="duration_min", color="label", barmode="overlay",
                                nbins=50, opacity=0.7, title="Trade Holding Period Distribution")
            fig4.update_layout(xaxis_title="Duration (minutes)", yaxis_title="Count", height=400)
            blocks.append(self._fig_html(fig4))

        # Grade performance
        merged = self._cat("merged")
        if not merged.empty and "grade" in merged.columns:
            grade_perf = merged.groupby(["label", "grade"], as_index=False).agg(
                trades_count=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            )
            fig_g = make_subplots(rows=1, cols=3,
                                   subplot_titles=("Net P&L by Grade", "Avg P&L", "Win Rate %"))
            for lbl in grade_perf["label"].unique():
                sub = grade_perf[grade_perf["label"] == lbl]
                fig_g.add_trace(go.Bar(x=sub["grade"], y=sub["net_pnl"], name=lbl), row=1, col=1)
                fig_g.add_trace(go.Bar(x=sub["grade"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=1, col=2)
                fig_g.add_trace(go.Bar(x=sub["grade"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=3)
            fig_g.update_layout(title="Grade Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig_g))

        # Top 10 best & worst
        for b in self.bundles:
            if b.trades.empty:
                continue
            show_cols = ["symbol", "sector", "direction", "entry_time", "realized_pnl", "exit_reason", "bars_in_trade"]
            show_cols = [c for c in show_cols if c in b.trades.columns]
            best = b.trades.nlargest(10, "realized_pnl")[show_cols]
            worst = b.trades.nsmallest(10, "realized_pnl")[show_cols]
            def _trade_table(df, title):
                header = "<tr>" + "".join(f"<th>{c}</th>" for c in show_cols) + "</tr>"
                rows = ""
                for _, r in df.iterrows():
                    color = _COLOR_WIN if r["realized_pnl"] > 0 else _COLOR_LOSS
                    cells = ""
                    for c in show_cols:
                        val = r[c]
                        if c == "realized_pnl":
                            cells += f"<td style='color:{color};font-weight:bold'>₹{val:,.0f}</td>"
                        else:
                            cells += f"<td>{val}</td>"
                    rows += f"<tr>{cells}</tr>"
                return f"<h3>{title}</h3><table class='score-table'><thead>{header}</thead><tbody>{rows}</tbody></table>"
            blocks.append(f"<div style='display:flex;gap:24px;flex-wrap:wrap'>"
                          f"<div style='flex:1;min-width:400px'>{_trade_table(best, f'Top 10 Best – {b.label}')}</div>"
                          f"<div style='flex:1;min-width:400px'>{_trade_table(worst, f'Top 10 Worst – {b.label}')}</div></div>")

        return "trades", blocks

    # ---- 8. Regime & VIX Analysis --------------------------------------------

    def _section_regime(self, js: bool) -> Tuple[str, List[str]]:
        merged = self._cat("merged")
        blocks: List[str] = []
        if merged.empty:
            return "regime", blocks

        if "regime" in merged.columns:
            rp = merged.groupby(["label", "regime"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            )
            fig = make_subplots(rows=1, cols=3,
                                subplot_titles=("Net P&L by Regime", "Win Rate %", "Trade Count"))
            for lbl in rp["label"].unique():
                sub = rp[rp["label"] == lbl]
                fig.add_trace(go.Bar(x=sub["regime"], y=sub["net_pnl"], name=lbl), row=1, col=1)
                fig.add_trace(go.Bar(x=sub["regime"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
                fig.add_trace(go.Bar(x=sub["regime"], y=sub["trades"], name=lbl, showlegend=False), row=1, col=3)
            fig.update_layout(title="Regime Performance", barmode="group", height=450)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # VIX bracket
        if "vix_percentile" in merged.columns:
            m = merged.dropna(subset=["vix_percentile"]).copy()
            m["vix_bracket"] = pd.cut(m["vix_percentile"],
                                       bins=[0, 20, 50, 75, 90, 100],
                                       labels=["Low (0-20)", "Normal (20-50)",
                                                "Elevated (50-75)", "High (75-90)", "Extreme (90+)"],
                                       include_lowest=True)
            vb = m.groupby(["label", "vix_bracket"], observed=True).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig_vb = make_subplots(rows=1, cols=2, subplot_titles=("Net P&L by VIX Bracket", "Win Rate %"))
            for lbl in vb["label"].unique():
                sub = vb[vb["label"] == lbl]
                fig_vb.add_trace(go.Bar(x=sub["vix_bracket"].astype(str), y=sub["net_pnl"], name=lbl), row=1, col=1)
                fig_vb.add_trace(go.Bar(x=sub["vix_bracket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig_vb.update_layout(title="VIX Bracket Performance", barmode="group", height=450)
            blocks.append(self._fig_html(fig_vb))

        # Nifty % vs P&L
        if "nifty_pct" in merged.columns:
            n = merged.dropna(subset=["nifty_pct"])
            if not n.empty:
                fig_np = px.scatter(n, x="nifty_pct", y="realized_pnl", color="label",
                                    opacity=0.3, trendline="ols",
                                    title="NIFTY % Change vs Trade P&L")
                fig_np.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_np.add_vline(x=0, line_dash="dash", line_color="gray")
                fig_np.update_layout(xaxis_title="NIFTY %", yaxis_title="P&L (INR)", height=450)
                blocks.append(self._fig_html(fig_np))

        # First trade effect
        for b in self.bundles:
            if b.trades.empty or b.daily.empty:
                continue
            t = b.trades.copy()
            t["trade_day"] = t["entry_time"].dt.date
            first_trades = t.sort_values("entry_time").groupby("trade_day").first().reset_index()
            first_trades["first_win"] = first_trades["realized_pnl"] > 0
            daily = b.daily.copy()
            daily["trade_day"] = daily["day"].dt.date
            day_merged = daily.merge(first_trades[["trade_day", "first_win"]], on="trade_day", how="inner")
            day_merged["first_outcome"] = np.where(day_merged["first_win"], "First Trade Win", "First Trade Loss")
            fig_ft = px.box(day_merged, x="first_outcome", y="pnl",
                            color="first_outcome",
                            color_discrete_map={"First Trade Win": _COLOR_WIN, "First Trade Loss": _COLOR_LOSS},
                            title=f"First Trade Effect on Day P&L – {b.label}",
                            points="outliers")
            fig_ft.update_layout(height=400, showlegend=False)
            blocks.append(self._fig_html(fig_ft))

        return "regime", blocks

    # ---- 9. Intraday Timing --------------------------------------------------

    def _section_timing(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "timing", blocks

        if "entry_hhmm" in trades.columns:
            fig = px.histogram(trades, x="entry_hhmm", color="label", barmode="overlay",
                               opacity=0.7, title="Entry Time Distribution")
            fig.update_layout(xaxis_title="Entry Time", yaxis_title="Count", height=400)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        bucket_perf = trades.groupby(["label", "entry_bucket"], as_index=False).agg(
            trades_count=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
        )
        fig2 = make_subplots(rows=2, cols=2,
                              subplot_titles=("Net P&L by Time Bucket", "Win Rate %",
                                              "Avg Trade P&L", "Trade Count"))
        for lbl in bucket_perf["label"].unique():
            sub = bucket_perf[bucket_perf["label"] == lbl]
            fig2.add_trace(go.Bar(x=sub["entry_bucket"], y=sub["net_pnl"], name=lbl), row=1, col=1)
            fig2.add_trace(go.Bar(x=sub["entry_bucket"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig2.add_trace(go.Bar(x=sub["entry_bucket"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=2, col=1)
            fig2.add_trace(go.Bar(x=sub["entry_bucket"], y=sub["trades_count"], name=lbl, showlegend=False), row=2, col=2)
        fig2.update_layout(title="Time Bucket Analysis", barmode="group", height=600)
        blocks.append(self._fig_html(fig2))

        # Entry hour × direction heatmap
        if "direction" in trades.columns:
            for lbl in trades["label"].unique():
                sub = trades[trades["label"] == lbl]
                hd = sub.groupby(["entry_hour", "direction"], as_index=False).agg(
                    avg_pnl=("realized_pnl", "mean"),
                )
                if not hd.empty:
                    pivot = hd.pivot_table(index="direction", columns="entry_hour", values="avg_pnl")
                    fig_hd = go.Figure(go.Heatmap(
                        z=pivot.values, x=[str(h) for h in pivot.columns],
                        y=pivot.index.tolist(),
                        colorscale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                        zmid=0, colorbar_title="Avg P&L",
                    ))
                    fig_hd.update_layout(title=f"Entry Hour × Direction Avg P&L – {lbl}",
                                         xaxis_title="Entry Hour", height=300)
                    blocks.append(self._fig_html(fig_hd))

        # Time bucket × exit reason
        if "exit_reason" in trades.columns:
            te = trades.groupby(["label", "entry_bucket", "exit_reason"], as_index=False).agg(
                count=("realized_pnl", "size"),
            )
            for lbl in te["label"].unique():
                sub = te[te["label"] == lbl]
                fig_te = px.bar(sub, x="entry_bucket", y="count", color="exit_reason",
                                barmode="stack",
                                title=f"Exit Reason by Entry Time Bucket – {lbl}")
                fig_te.update_layout(height=400)
                blocks.append(self._fig_html(fig_te))

        return "timing", blocks

    # ---- 10. Sector Analysis --------------------------------------------------

    def _section_sectors(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty or "sector" not in trades.columns:
            return "sectors", blocks

        # Sector performance heatmap
        for lbl in trades["label"].unique():
            sub = trades[trades["label"] == lbl]
            sp = sub.groupby("sector", as_index=False).agg(
                trades_count=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                avg_bars=("bars_in_trade", "mean"),
            )
            sp = sp.sort_values("net_pnl", ascending=True)
            metrics = ["net_pnl", "avg_pnl", "win_rate", "trades_count", "avg_bars"]
            z_data = []
            for m in metrics:
                vals = sp[m].values
                z_data.append((vals - vals.mean()) / vals.std() if vals.std() > 0 else vals * 0)
            fig = go.Figure(go.Heatmap(
                z=np.array(z_data),
                x=sp["sector"].tolist(),
                y=["Net P&L", "Avg P&L", "Win Rate %", "Trade Count", "Avg Bars"],
                colorscale="RdYlGn", zmid=0,
            ))
            fig.update_layout(title=f"Sector Performance Heatmap – {lbl}",
                              height=380, xaxis_tickangle=45)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Sector P&L sorted bar
        sector_total = trades.groupby(["label", "sector"], as_index=False)["realized_pnl"].sum()
        sector_sort = sector_total.groupby("sector")["realized_pnl"].sum().sort_values()
        sector_order = sector_sort.index.tolist()
        sector_total["sector"] = pd.Categorical(sector_total["sector"], categories=sector_order, ordered=True)
        fig2 = px.bar(sector_total.sort_values("sector"), x="realized_pnl", y="sector", color="label",
                       barmode="group", orientation="h", title="Sector Net P&L (Sorted)")
        fig2.update_layout(height=max(400, len(sector_order) * 25 + 100))
        blocks.append(self._fig_html(fig2))

        # Sector trade treemap
        for b in self.bundles:
            if b.trades.empty:
                continue
            st = b.trades.groupby("sector", as_index=False).agg(
                trades_count=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
            )
            fig_tm = px.treemap(st, path=["sector"], values="trades_count", color="net_pnl",
                                color_continuous_scale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                                color_continuous_midpoint=0,
                                title=f"Sector Treemap – {b.label}")
            fig_tm.update_layout(height=500)
            blocks.append(self._fig_html(fig_tm))

        # Sector × Direction
        if "direction" in trades.columns:
            sd = trades.groupby(["label", "sector", "direction"], as_index=False).agg(
                net_pnl=("realized_pnl", "sum"),
                trades_count=("realized_pnl", "size"),
            )
            for lbl in sd["label"].unique():
                sub = sd[sd["label"] == lbl]
                top_sectors = sub.groupby("sector")["trades_count"].sum().nlargest(10).index.tolist()
                sub = sub[sub["sector"].isin(top_sectors)]
                fig_sd = px.bar(sub, x="sector", y="net_pnl", color="direction",
                                barmode="group",
                                title=f"Sector × Direction P&L (Top 10) – {lbl}")
                fig_sd.update_layout(height=400, xaxis_tickangle=45)
                blocks.append(self._fig_html(fig_sd))

        # Sector × exit reason distribution
        for b in self.bundles:
            if b.trades.empty:
                continue
            se = b.trades.groupby(["sector", "exit_reason"], as_index=False).agg(count=("realized_pnl", "size"))
            top_sec = b.trades.groupby("sector")["realized_pnl"].count().nlargest(8).index.tolist()
            se = se[se["sector"].isin(top_sec)]
            if not se.empty:
                fig_se = px.bar(se, x="sector", y="count", color="exit_reason",
                                barmode="stack",
                                title=f"Sector × Exit Reason – {b.label}")
                fig_se.update_layout(height=400, xaxis_tickangle=45)
                blocks.append(self._fig_html(fig_se))

        return "sectors", blocks

    # ---- 11. Execution Funnel ------------------------------------------------

    def _section_funnel(self, js: bool) -> Tuple[str, List[str]]:
        blocks: List[str] = []

        for b in self.bundles:
            summary = b.summary
            all_sigs = int(summary.get("all_signals", 0))
            gate_blocked = int(summary.get("total_gate_blocked", 0))
            gate_passed = all_sigs - gate_blocked
            executed = int(summary.get("executed_signals", 0))
            wins = int(summary.get("wins", 0))

            stages = ["All A+ Signals", "Gate Passed", "Executed", "Profitable"]
            values = [all_sigs, gate_passed, executed, wins]

            fig = go.Figure(go.Funnel(
                y=stages, x=values,
                textposition="inside",
                textinfo="value+percent initial",
                marker=dict(color=["#3b82f6", "#8b5cf6", "#22c55e", "#10b981"]),
            ))
            fig.update_layout(title=f"Execution Funnel – {b.label}", height=450)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Decision breakdown
        rows: List[Dict[str, Any]] = []
        for b in self.bundles:
            dc = b.summary.get("decision_counts") or {}
            for k, v in dc.items():
                rows.append({"label": b.label, "reason": _norm_reason(k), "count": int(v)})
        if rows:
            df = pd.DataFrame(rows)
            totals = df.groupby("reason", as_index=False)["count"].sum().sort_values("count", ascending=False)
            top = set(totals.head(12)["reason"].tolist())
            df["reason"] = np.where(df["reason"].isin(top), df["reason"], "OTHER")
            df = df.groupby(["label", "reason"], as_index=False)["count"].sum()
            fig2 = px.bar(df, x="label", y="count", color="reason", barmode="stack",
                           title="Entry Decision Breakdown")
            fig2.update_layout(height=450)
            blocks.append(self._fig_html(fig2))

        # Risk reason breakdown
        rows2: List[Dict[str, Any]] = []
        for b in self.bundles:
            rc = b.summary.get("risk_reason_counts") or {}
            for k, v in rc.items():
                rows2.append({"label": b.label, "reason": _norm_reason(k), "count": int(v)})
        if rows2:
            df2 = pd.DataFrame(rows2)
            fig3 = px.bar(df2, x="label", y="count", color="reason", barmode="stack",
                           title="Risk Rejection Reason Breakdown")
            fig3.update_layout(height=450)
            blocks.append(self._fig_html(fig3))

        # Daily trade count vs max position limit
        for b in self.bundles:
            if b.daily.empty or b.trades.empty:
                continue
            d = b.daily.copy()
            t = b.trades.copy()
            t["trade_day"] = t["entry_time"].dt.date
            daily_trades = t.groupby("trade_day").size().reset_index(name="active_trades")
            d["trade_day"] = d["day"].dt.date
            d = d.merge(daily_trades, on="trade_day", how="left").fillna(0)
            max_pos = b.config.get("MAX_CONCURRENT_POSITIONS", 6)
            fig4 = go.Figure()
            fig4.add_trace(go.Bar(x=d["day"], y=d["active_trades"],
                                   name="Trades/Day", marker_color="#3b82f6", opacity=0.7))
            fig4.add_hline(y=max_pos, line_dash="dash", line_color="red",
                           annotation_text=f"Max Positions: {max_pos}")
            fig4.update_layout(title=f"Daily Trade Count vs Max Positions – {b.label}",
                               yaxis_title="Trade Count", height=350)
            blocks.append(self._fig_html(fig4))

        return "funnel", blocks

    # ---- 12. Risk & Position Sizing ------------------------------------------

    def _section_risk(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "risk", blocks

        # Risk per trade
        if "entry_risk_per_share" in trades.columns and "initial_qty" in trades.columns:
            t = trades.copy()
            t["trade_risk"] = (t["entry_risk_per_share"] * t["initial_qty"]).abs()
            t = t.dropna(subset=["trade_risk"])
            if not t.empty:
                fig = px.histogram(t, x="trade_risk", color="label", barmode="overlay",
                                   nbins=40, opacity=0.7, title="Total Risk Per Trade (INR)")
                fig.update_layout(xaxis_title="Risk Amount (INR)", height=400)
                blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Notional vs P&L
        if "notional_at_entry" in trades.columns:
            fig3 = px.scatter(trades.dropna(subset=["notional_at_entry"]),
                              x="notional_at_entry", y="realized_pnl", color="label",
                              opacity=0.3, title="Notional at Entry vs P&L")
            fig3.add_hline(y=0, line_dash="dash", line_color="gray")
            fig3.update_layout(xaxis_title="Notional (INR)", yaxis_title="P&L (INR)", height=400)
            blocks.append(self._fig_html(fig3))

        # Sector notional concentration
        if "notional_at_entry" in trades.columns:
            for b in self.bundles:
                if b.trades.empty:
                    continue
                sc = b.trades.groupby("sector", as_index=False)["notional_at_entry"].sum()
                sc = sc.sort_values("notional_at_entry", ascending=False)
                fig5 = px.pie(sc, names="sector", values="notional_at_entry",
                              title=f"Sector Notional Concentration – {b.label}")
                fig5.update_layout(height=450)
                blocks.append(self._fig_html(fig5))

        # LONG vs SHORT split
        dir_perf = trades.groupby(["label", "direction"], as_index=False).agg(
            trades_count=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
        )
        fig6 = make_subplots(rows=1, cols=3,
                              subplot_titles=("Net P&L", "Avg P&L", "Win Rate %"))
        for lbl in dir_perf["label"].unique():
            sub = dir_perf[dir_perf["label"] == lbl]
            fig6.add_trace(go.Bar(x=sub["direction"], y=sub["net_pnl"], name=lbl), row=1, col=1)
            fig6.add_trace(go.Bar(x=sub["direction"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=1, col=2)
            fig6.add_trace(go.Bar(x=sub["direction"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=3)
        fig6.update_layout(title="LONG vs SHORT Performance", barmode="group", height=400)
        blocks.append(self._fig_html(fig6))

        return "risk", blocks

    # ---- 13. Parameter Optimization ------------------------------------------

    def _section_params(self, js: bool) -> Tuple[str, List[str]]:
        sdf = self.summary_df
        blocks: List[str] = []
        if sdf.empty or len(sdf) < 2:
            blocks.append("<p class='muted'>Parameter optimization requires 2+ runs.</p>")
            return "params", blocks

        metrics = ["total_return_pct", "win_rate_pct", "profit_factor", "avg_trade_pnl"]
        metric_names = ["Return %", "Win Rate %", "Profit Factor", "Avg P&L"]
        avail_metrics = [m for m in metrics if m in sdf.columns]
        avail_metric_names = [metric_names[i] for i, m in enumerate(metrics) if m in sdf.columns]

        param_corrs: List[Dict[str, Any]] = []
        for pk in PARAM_KEYS:
            if pk not in sdf.columns:
                continue
            vals = pd.to_numeric(sdf[pk], errors="coerce")
            if vals.notna().sum() < 2 or vals.nunique(dropna=True) < 2:
                continue
            row_data = {"param": pk}
            for m in avail_metrics:
                mv = pd.to_numeric(sdf[m], errors="coerce")
                valid = vals.notna() & mv.notna()
                if valid.sum() >= 2:
                    row_data[m] = float(vals[valid].corr(mv[valid]))
                else:
                    row_data[m] = 0.0
            param_corrs.append(row_data)

        if param_corrs:
            pdf = pd.DataFrame(param_corrs)
            z_vals = pdf[avail_metrics].values
            fig = go.Figure(go.Heatmap(
                z=z_vals, x=avail_metric_names,
                y=pdf["param"].tolist(),
                colorscale="RdBu_r", zmid=0, colorbar_title="Correlation",
            ))
            fig.update_layout(title="Parameter × Metric Correlation Matrix",
                              height=max(300, len(pdf) * 25 + 100))
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # VIX multiplier comparison
        vix_params = ["VIX_MULT_LOW", "VIX_MULT_NORMAL", "VIX_MULT_ELEVATED",
                      "VIX_MULT_HIGH", "VIX_MULT_EXTREME"]
        vix_avail = [p for p in vix_params if p in sdf.columns]
        if len(vix_avail) >= 3:
            vix_rows = []
            for _, r in sdf.iterrows():
                for p in vix_avail:
                    vix_rows.append({"label": r["label"], "bracket": p.replace("VIX_MULT_", ""), "multiplier": _f(r.get(p))})
            fig4 = px.bar(pd.DataFrame(vix_rows), x="bracket", y="multiplier", color="label",
                           barmode="group", title="VIX Multiplier Configuration")
            fig4.update_layout(height=400)
            blocks.append(self._fig_html(fig4))

        # V6.9 exit config comparison
        exit_params = ["V6_9_STOP_ATR_MULT_5M", "V6_9_STOP_MIN_PCT",
                       "V6_9_HMA_TRAIL_BUFFER_ATR", "V6_9_TARGET_1_R", "V6_9_TARGET_1_EXIT_PCT"]
        exit_avail = [p for p in exit_params if p in sdf.columns and sdf[p].notna().any()]
        if exit_avail:
            exit_rows = []
            for _, r in sdf.iterrows():
                for p in exit_avail:
                    exit_rows.append({"label": r["label"], "param": p.replace("V6_9_", ""), "value": _f(r.get(p))})
            fig5 = px.bar(pd.DataFrame(exit_rows), x="param", y="value", color="label",
                           barmode="group", title="V6.9 Exit System Configuration")
            fig5.update_layout(height=400, xaxis_tickangle=25)
            blocks.append(self._fig_html(fig5))

        # HMA config comparison
        hma_params = ["V6_6_HMA_FAST", "V6_6_HMA_SLOW",
                      "V6_7_CROSS_FRESHNESS_BARS", "V6_7_SLOPE_LOOKBACK",
                      "V6_7_MIN_HMA_SEP_ATR_FRAC"]
        hma_avail = [p for p in hma_params if p in sdf.columns and sdf[p].notna().any()]
        if hma_avail:
            hma_rows = []
            for _, r in sdf.iterrows():
                for p in hma_avail:
                    hma_rows.append({"label": r["label"], "param": p.replace("V6_", ""), "value": _f(r.get(p))})
            fig6 = px.bar(pd.DataFrame(hma_rows), x="param", y="value", color="label",
                           barmode="group", title="HMA & Quality Gate Configuration")
            fig6.update_layout(height=400, xaxis_tickangle=25)
            blocks.append(self._fig_html(fig6))

        # Sector weight comparison
        sw_params = [p for p in PARAM_KEYS if p.startswith("SECTOR_WEIGHTS.")]
        sw_avail = [p for p in sw_params if p in sdf.columns and sdf[p].notna().any()]
        if sw_avail:
            sw_rows = []
            for _, r in sdf.iterrows():
                for p in sw_avail:
                    sw_rows.append({"label": r["label"], "weight": p.replace("SECTOR_WEIGHTS.", ""), "value": _f(r.get(p))})
            fig7 = px.bar(pd.DataFrame(sw_rows), x="weight", y="value", color="label",
                           barmode="group", title="Sector Scoring Weights")
            fig7.update_layout(height=400)
            blocks.append(self._fig_html(fig7))

        return "params", blocks

    # ══════════════════════════════════════════════════════════════════════════
    # HTML Builder
    # ══════════════════════════════════════════════════════════════════════════

    def build_html(self, output_path: Path,
                   title: str = "V6.9 PRO Backtest Graph Analysis") -> Path:
        builder_map = {
            "summary":   self._section_summary,
            "equity":    self._section_equity,
            "hma_exit":  self._section_hma_exit,
            "quality":   self._section_quality,
            "calendar":  self._section_calendar,
            "direction": self._section_direction,
            "trades":    self._section_trades,
            "regime":    self._section_regime,
            "timing":    self._section_timing,
            "sectors":   self._section_sectors,
            "funnel":    self._section_funnel,
            "risk":      self._section_risk,
            "params":    self._section_params,
        }

        all_blocks: List[Tuple[str, str, List[str]]] = []
        need_js = True
        total_charts = 0
        for sec_id, sec_title in self.SECTIONS:
            print(f"  Building section: {sec_title} ...")
            _, blocks = builder_map[sec_id](js=need_js)
            if blocks:
                need_js = False
            total_charts += len(blocks)
            all_blocks.append((sec_id, sec_title, blocks))

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_list = "".join(f"<li><strong>{b.label}</strong>: {b.path.name}</li>" for b in self.bundles)

        nav_links = "".join(
            f'<a href="#{sid}" class="nav-link">{stitle}</a>'
            for sid, stitle, blocks in all_blocks if blocks
        )

        section_html = ""
        for sid, stitle, blocks in all_blocks:
            if not blocks:
                continue
            cards = "\n".join(f'<div class="chart-card">{b}</div>' for b in blocks)
            section_html += f"""
            <section id="{sid}" class="section">
                <h2 class="section-title">{stitle}</h2>
                {cards}
            </section>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>
:root {{
    --bg: #f1f5f9; --card: #ffffff; --text: #0f172a;
    --muted: #64748b; --accent: #3b82f6; --border: #e2e8f0;
    --nav-bg: #1e293b; --nav-text: #e2e8f0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
}}
.top-nav {{
    position: sticky; top: 0; z-index: 1000;
    background: var(--nav-bg); padding: 10px 24px;
    display: flex; flex-wrap: wrap; gap: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    align-items: center;
}}
.top-nav .brand {{
    color: #fff; font-weight: 700; font-size: 1.1rem;
    margin-right: 16px; white-space: nowrap;
}}
.nav-link {{
    color: var(--nav-text); text-decoration: none; font-size: 0.82rem;
    padding: 4px 10px; border-radius: 6px; transition: background 0.15s;
    white-space: nowrap;
}}
.nav-link:hover {{ background: rgba(255,255,255,0.12); }}
.container {{ max-width: 1600px; margin: 0 auto; padding: 24px; }}
.header-card {{
    background: var(--card); border-radius: 12px; padding: 24px;
    margin-bottom: 24px; box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}}
.header-card h1 {{ font-size: 1.6rem; margin-bottom: 8px; }}
.header-card .meta {{ color: var(--muted); font-size: 0.9rem; }}
.section {{ margin-bottom: 32px; }}
.section-title {{
    font-size: 1.25rem; margin-bottom: 16px;
    padding-bottom: 8px; border-bottom: 2px solid var(--accent);
    color: var(--accent);
}}
.chart-card {{
    background: var(--card); border-radius: 10px; padding: 16px;
    margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    overflow-x: auto;
}}
.score-table {{
    border-collapse: collapse; width: 100%; font-size: 0.85rem;
}}
.score-table th {{
    background: var(--nav-bg); color: var(--nav-text);
    padding: 8px 12px; text-align: left; white-space: nowrap;
}}
.score-table td {{
    padding: 6px 12px; border-bottom: 1px solid var(--border);
    white-space: nowrap;
}}
.score-table tr:hover {{ background: #f8fafc; }}
h3 {{ font-size: 1rem; margin-bottom: 8px; color: var(--text); }}
.muted {{ color: var(--muted); font-size: 0.9rem; }}
</style>
</head>
<body>
<nav class="top-nav">
    <span class="brand">V6.9 PRO Dashboard</span>
    {nav_links}
</nav>
<div class="container">
    <div class="header-card">
        <h1>{title}</h1>
        <p class="meta">Generated: {generated_at} &nbsp;|&nbsp; Runs: {len(self.bundles)} &nbsp;|&nbsp; Charts: {total_charts}</p>
        <ul style="margin-top:8px;font-size:0.9rem;">{file_list}</ul>
    </div>
    {section_html}
</div>
</body>
</html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-discovery & CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _dedupe(paths: Iterable[Path]) -> List[Path]:
    seen: set = set()
    out: List[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out


def _discover(sources: Sequence[Dict[str, Any]]) -> Tuple[List[Path], List[str]]:
    files: List[Path] = []
    labels: List[str] = []
    for src in sources:
        raw = src.get("path", src.get("dir", ""))
        sp = Path(raw)
        lbl = str(src.get("label", sp.name))
        if not sp.exists():
            continue
        if sp.is_file():
            if sp.name.startswith("backtest_history_") and sp.suffix.lower() == ".json":
                files.append(sp.resolve())
                labels.append(lbl)
            continue
        candidates = sorted(sp.glob("backtest_history_*.json"))
        if candidates:
            files.append(candidates[-1].resolve())
            labels.append(lbl)
    return _dedupe(files), labels


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V6.9 PRO Graph Analyzer")
    p.add_argument("history_files", nargs="*", help="History JSON file paths")
    p.add_argument("--labels", nargs="*", help="Labels (same order as files)")
    p.add_argument("--output", default="", help="Output HTML path")
    p.add_argument("--title", default="V6.9 PRO Backtest Graph Analysis")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    explicit = [Path(p) for p in args.history_files]

    if explicit:
        all_files = _dedupe(explicit)
        labels: Optional[List[str]] = None
        if args.labels:
            if len(args.labels) != len(explicit):
                print("Error: --labels count must match file count")
                return 1
            lmap = {p.resolve(): l for p, l in zip(explicit, args.labels)}
            labels = [lmap.get(f, _safe_label(f)) for f in all_files]
    else:
        all_files, auto_labels = _discover(DEFAULT_HISTORY_SOURCES)
        labels = auto_labels

    if not all_files:
        print("No history files found.")
        return 1

    stamp = datetime.now().strftime("%d-%m-%Y_%I-%M_%p").lower()
    output = Path(args.output) if args.output else (ROOT / "analysis" / f"pro_v69_graph_analysis_{stamp}.html")

    print(f"Loading {len(all_files)} history files ...")
    analyzer = ProGraphAnalyzerV3(all_files, labels=labels)
    analyzer.load()

    print("Building dashboard ...")
    out = analyzer.build_html(output_path=output, title=args.title)

    print(f"\nDashboard exported: {out}")
    print(f"Runs analyzed: {len(analyzer.bundles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
