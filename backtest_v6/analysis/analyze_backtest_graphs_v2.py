"""
V6 PRO Graph-Based Backtest Analyzer  (v2)
============================================
Generates an expert-level interactive HTML dashboard with 50+ professional
charts across 12 analytical sections.  Covers equity journeys, direction-
alignment matrices (index × sector × signal), MFE/MAE edge analysis, regime
decomposition, parameter optimisation surfaces, execution funnels, calendar
heatmaps, and much more.

Usage
-----
    # Uses DEFAULT_HISTORY_SOURCES list (edit below)
    python analyze_backtest_graphs_v2.py

    # Explicit files with custom labels
    python analyze_backtest_graphs_v2.py file1.json file2.json --labels Run_A Run_B

    # Custom output path
    python analyze_backtest_graphs_v2.py --output dashboard.html
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
    # Each item supports:
    #   - a directory path (latest backtest_history_*.json is auto-selected)
    #   - a direct JSON file path
    # {"path": ROOT / "history", "label": "v6.0"},
    # {"path": ROOT / "history_v6.1", "label": "v6.1"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_24-02-2026_08-33_am.json", "label": "v6.2_run1"},
    # {"path": ROOT / "history_v6.4" / "backtest_history_24-02-2026_04-09_pm.json", "label": "v6.4_run1"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_07-30_am.json", "label": "v6.2_run2"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_09-11_am.json", "label": "v6.2_run3"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_10-58_am.json", "label": "v6.2_run4"},
    {"path": ROOT / "history_v6.8" / "backtest_history_27-02-2026_04-55_pm.json", "label": "2025"},
    {"path": ROOT / "history_v6.8" / "backtest_history_27-02-2026_04-54_pm.json", "label": "2024"},
    {"path": ROOT / "history_v6.8" / "backtest_history_27-02-2026_04-53_pm.json", "label": "2023"},
    # {"path": ROOT / "history_v6.3", "label": "v6.3"},
    # {"path": ROOT / "history_v6.4", "label": "v6.4"},
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


PARAM_KEYS = [
    "BASE_RISK_PER_TRADE_PCT", "MAX_CONCURRENT_POSITIONS",
    "MAX_POSITIONS_PER_SECTOR", "MAX_POSITIONS_PER_STOCK",
    "STOP_ATR_MULT", "TARGET_1_MULT", "TARGET_1_EXIT_PCT",
    "CHANDELIER_ATR_MULT", "CHANDELIER_LOOKBACK",
    "RISK_MULT_LUNCH", "RISK_MULT_WARNING",
    "MIN_ADV_CRORES", "SPREAD_ATR_LIMIT",
    "THRESHOLD_A_PLUS", "THRESHOLD_A", "THRESHOLD_B",
    "POINTS_HMA", "POINTS_RVOL", "POINTS_STOCH",
    "POINTS_SECTOR_RANK", "POINTS_SPREAD",
    "VIX_MULT_LOW", "VIX_MULT_NORMAL", "VIX_MULT_ELEVATED",
    "VIX_MULT_HIGH", "VIX_MULT_EXTREME",
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
# Loader
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
        for c in ("realized_pnl", "gross_pnl", "entry_price", "notional_at_entry", "total_turnover", "total_charges",
                   "entry_risk_per_share", "entry_atr_5m", "mfe_r", "mae_r"):
            if c in trades.columns:
                trades[c] = pd.to_numeric(trades[c], errors="coerce")
        if "brokerage_breakdown" in trades.columns:
            breakdown = pd.json_normalize(trades["brokerage_breakdown"]).add_prefix("charge_")
            if not breakdown.empty:
                trades = pd.concat([trades.drop(columns=["brokerage_breakdown"]), breakdown], axis=1)
        for c in ("charge_brokerage", "charge_stt", "charge_transaction_charge", "charge_sebi_charge", "charge_stamp_charge", "charge_gst"):
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
            labels=["OPEN 09:25-10:30", "MID 10:30-12:00", "LUNCH 12:00-13:15",
                     "AFTERNOON 13:15-14:05", "LATE 14:05+"],
            include_lowest=True,
        ).astype(str)
        trades["label"] = label

    # --- signals (v6.8 may not include all_signal_records; fallback to signal_records) ---
    signal_source = data.get("all_signal_records")
    if signal_source is None:
        signal_source = data.get("signal_records", [])
    signals = pd.DataFrame(signal_source)
    if not signals.empty:
        signals["label"] = label
        signals["timestamp"] = pd.to_datetime(signals.get("timestamp"), errors="coerce")
        signals["day"] = signals["timestamp"].dt.date
        for c in ("score", "rvol", "stoch_k", "vix_percentile", "nifty_pct",
                   "change_pct", "adv_crores", "atr", "price", "spread_atr",
                   "vix_ltp", "vix_multiplier", "nifty_ltp"):
            if c in signals.columns:
                signals[c] = pd.to_numeric(signals[c], errors="coerce")
        if "sector_rank" in signals.columns:
            signals["sector_rank"] = pd.to_numeric(signals["sector_rank"], errors="coerce")

    # --- positions ---
    position_source = data.get("all_position_records")
    if position_source is None:
        position_source = data.get("position_records", [])
    positions = pd.DataFrame(position_source)
    if not positions.empty:
        positions["label"] = label
        for c in ("entry_price", "atr", "stop_price", "target_1", "sizing_shares",
                   "risk_amount", "risk_per_share", "effective_risk_pct", "notional"):
            if c in positions.columns:
                positions[c] = pd.to_numeric(positions[c], errors="coerce")

    # --- merge trades + signals for enriched analysis ---
    merged = pd.DataFrame()
    if not trades.empty and not signals.empty and "executed_trade_id" in signals.columns:
        executed = signals[signals["executed_trade"] == True].copy()
        if not executed.empty:
            sig_cols = ["executed_trade_id", "regime", "score", "grade", "rvol",
                        "stoch_k", "sector_rank", "vix_ltp", "vix_percentile",
                        "nifty_pct", "change_pct", "hma_align", "spread_atr",
                        "adv_crores", "atr", "vix_multiplier", "nifty_ltp"]
            sig_cols = [c for c in sig_cols if c in executed.columns]
            sig_lookup = executed[sig_cols].drop_duplicates("executed_trade_id")
            merged = trades.merge(
                sig_lookup, left_on="trade_id", right_on="executed_trade_id", how="left",
                suffixes=("", "_sig"),
            )
    if merged.empty:
        merged = trades.copy()

    # Compute per-trade sector direction from signals
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

    if not merged.empty:
        if "nifty_pct" in merged.columns:
            merged["index_dir"] = np.where(merged["nifty_pct"] > 0, "UP", "DOWN")
        if "direction" in merged.columns:
            merged["signal_dir"] = np.where(merged["direction"] == "LONG", "UP", "DOWN")

    # --- summary row ---
    wins = int((trades["realized_pnl"] > 0).sum()) if not trades.empty else 0
    losses = int((trades["realized_pnl"] < 0).sum()) if not trades.empty else 0
    gp = float(trades.loc[trades["realized_pnl"] > 0, "realized_pnl"].sum()) if not trades.empty else 0
    gl = float(trades.loc[trades["realized_pnl"] < 0, "realized_pnl"].sum()) if not trades.empty else 0
    pf = (gp / abs(gl)) if gl < 0 else float("nan")
    all_signals = int(_f(summary.get("all_a_grade_signals", 0)))
    if all_signals <= 0:
        all_signals = len(signals)
    executed_signals = int(_f(summary.get("executed_positions", 0)))
    if executed_signals <= 0:
        executed_signals = len(trades)

    exchange = (
        summary.get("exchange")
        or data.get("inputs", {}).get("exchange")
        or config.get("V6_8_EXCHANGE")
        or "UNKNOWN"
    )
    transaction_charge_pct = _f(
        summary.get("transaction_charge_pct", data.get("inputs", {}).get("transaction_charge_pct", 0.0))
    )
    total_turnover = _f(summary.get("total_turnover", 0.0))
    if total_turnover <= 0 and not trades.empty:
        total_turnover = float(trades["total_turnover"].sum())
    total_charges = _f(summary.get("total_charges", 0.0))
    if total_charges <= 0 and not trades.empty:
        total_charges = float(trades["total_charges"].sum())
    charge_breakdown = summary.get("brokerage_breakdown") or {}
    charge_brokerage = _f(charge_breakdown.get("brokerage", float(trades["charge_brokerage"].sum()) if "charge_brokerage" in trades.columns else 0.0))
    charge_stt = _f(charge_breakdown.get("stt", float(trades["charge_stt"].sum()) if "charge_stt" in trades.columns else 0.0))
    charge_transaction = _f(charge_breakdown.get("transaction_charge", float(trades["charge_transaction_charge"].sum()) if "charge_transaction_charge" in trades.columns else 0.0))
    charge_sebi = _f(charge_breakdown.get("sebi_charge", float(trades["charge_sebi_charge"].sum()) if "charge_sebi_charge" in trades.columns else 0.0))
    charge_stamp = _f(charge_breakdown.get("stamp_charge", float(trades["charge_stamp_charge"].sum()) if "charge_stamp_charge" in trades.columns else 0.0))
    charge_gst = _f(charge_breakdown.get("gst", float(trades["charge_gst"].sum()) if "charge_gst" in trades.columns else 0.0))
    gross_return_before_charges = _f(summary.get("gross_return_before_charges", _f(summary.get("total_return", 0.0)) + total_charges))

    row: Dict[str, Any] = {
        "label": label, "path": str(path),
        "run_id": run_meta.get("run_id", ""),
        "status": run_meta.get("status", ""),
        "start_date": run_meta.get("start_date", ""),
        "end_date": run_meta.get("end_date", ""),
        "initial_equity": _f(summary.get("initial_equity")),
        "final_equity": _f(summary.get("final_equity")),
        "total_return": _f(summary.get("total_return")),
        "gross_return_before_charges": gross_return_before_charges,
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
        "transaction_charge_pct": transaction_charge_pct,
        "total_turnover": total_turnover,
        "total_charges": total_charges,
        "charges_pct_turnover": round(_pct(total_charges, total_turnover), 4),
        "charge_brokerage": charge_brokerage,
        "charge_stt": charge_stt,
        "charge_transaction": charge_transaction,
        "charge_sebi": charge_sebi,
        "charge_stamp": charge_stamp,
        "charge_gst": charge_gst,
        "execution_rate_pct": round(_pct(
            executed_signals,
            all_signals,
        ), 2),
        "blocked_count": int(_f(summary.get("blocked_by_max_positions_count", 0))),
        "decision_counts": summary.get("decision_counts") or {},
        "risk_reason_counts": summary.get("risk_reason_counts") or {},
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
    for k in PARAM_KEYS:
        row[k] = _extract_param(config, k)

    return RunBundle(label=label, path=path, raw=data, summary=row,
                     config=config, daily=daily, trades=trades,
                     signals=signals, positions=positions, merged=merged)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class ProGraphAnalyzer:

    SECTIONS = [
        ("summary",   "1. Executive Summary"),
        ("equity",    "2. Equity & Drawdown Journey"),
        ("calendar",  "3. Calendar & Temporal Patterns"),
        ("direction", "4. Direction Alignment Matrix"),
        ("trades",    "5. Trade Deep Dive"),
        ("regime",    "6. Regime & VIX Analysis"),
        ("timing",    "7. Intraday Timing Patterns"),
        ("sectors",   "8. Sector Analysis"),
        ("signals",   "9. Signal Quality & Indicators"),
        ("funnel",    "10. Execution Funnel"),
        ("risk",      "11. Risk & Position Sizing"),
        ("params",    "12. Parameter Optimization"),
    ]

    def __init__(self, files: Sequence[Path], labels: Optional[Sequence[str]] = None):
        self.files = list(files)
        self.labels = list(labels) if labels else []
        self.bundles: List[RunBundle] = []

    def load(self) -> None:
        self.bundles.clear()
        for i, fp in enumerate(self.files):
            lbl = self.labels[i] if self.labels else _safe_label(fp)
            self.bundles.append(_load_bundle(fp, lbl))
        print(f"  Loaded {len(self.bundles)} runs")

    # ── concat helpers ────────────────────────────────────────────────────────

    @property
    def summary_df(self) -> pd.DataFrame:
        return pd.DataFrame([b.summary for b in self.bundles])

    def _cat(self, attr: str) -> pd.DataFrame:
        frames = [getattr(b, attr) for b in self.bundles if not getattr(b, attr).empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION BUILDERS – each returns List[Tuple[str, str]]
    #   where each tuple is (chart_title, html_block)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _fig_html(fig: go.Figure, js: bool = False) -> str:
        fig.update_layout(template=_PLOTLY_TEMPLATE, legend_title_text="",
                          margin=dict(l=60, r=30, t=50, b=50))
        return fig.to_html(full_html=False,
                           include_plotlyjs=("cdn" if js else False),
                           config={"displaylogo": False})

    # ---- 1. Executive Summary ------------------------------------------------

    def _section_summary(self, js: bool) -> Tuple[str, List[str]]:
        sdf = self.summary_df
        blocks: List[str] = []

        # -- scorecard table --
        cols = [
            ("label", "Run"), ("start_date", "Start"), ("end_date", "End"),
            ("trading_days", "Days"), ("closed_trades", "Trades"),
            ("win_rate_pct", "Win %"), ("profit_factor", "PF"),
            ("total_return_pct", "Return %"), ("max_dd_pct", "Max DD %"),
            ("avg_trade_pnl", "Avg PnL"), ("execution_rate_pct", "Exec %"),
            ("total_charges", "Charges"), ("charges_pct_turnover", "Charge % TO"),
            ("sharpe_daily", "Sharpe"), ("avg_r", "Avg R"),
        ]
        avail = [(k, n) for k, n in cols if k in sdf.columns]
        header = "".join(f"<th>{n}</th>" for _, n in avail)
        rows_html = ""
        for _, r in sdf.iterrows():
            cells = "".join(
                f"<td>{r.get(k, '')}</td>" if k == 'label'
                else f"<td>{r.get(k, ''):.2f}</td>" if isinstance(r.get(k), float)
                else f"<td>{r.get(k, '')}</td>"
                for k, _ in avail
            )
            rows_html += f"<tr>{cells}</tr>"
        blocks.append(f"""
        <div style="overflow-x:auto;">
        <table class="score-table"><thead><tr>{header}</tr></thead>
        <tbody>{rows_html}</tbody></table></div>""")

        # -- radar chart --
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

        if "total_charges" in sdf.columns:
            fig_cost = px.bar(
                sdf.sort_values("total_charges", ascending=False),
                x="label",
                y="total_charges",
                color="label",
                title="Total Brokerage/Statutory Charges by Run",
                text_auto=".2s",
            )
            fig_cost.update_layout(showlegend=False, yaxis_title="Charges (INR)", height=360)
            blocks.append(self._fig_html(fig_cost))

        charge_cols = [
            ("charge_brokerage", "Brokerage"),
            ("charge_stt", "STT/CTT"),
            ("charge_transaction", "Transaction"),
            ("charge_sebi", "SEBI"),
            ("charge_stamp", "Stamp"),
            ("charge_gst", "GST"),
        ]
        if all(c in sdf.columns for c, _ in charge_cols):
            rows = []
            for _, r in sdf.iterrows():
                for c, name in charge_cols:
                    rows.append({"label": r["label"], "component": name, "value": _f(r.get(c))})
            cdf = pd.DataFrame(rows)
            fig_break = px.bar(
                cdf,
                x="label",
                y="value",
                color="component",
                barmode="stack",
                title="Charge Component Breakdown by Run",
            )
            fig_break.update_layout(yaxis_title="Charges (INR)", height=380)
            blocks.append(self._fig_html(fig_break))

        return "summary", blocks

    # ---- 2. Equity & Drawdown ------------------------------------------------

    def _section_equity(self, js: bool) -> Tuple[str, List[str]]:
        daily = self._cat("daily")
        blocks: List[str] = []
        if daily.empty:
            return "equity", blocks

        # Equity Curve + Drawdown dual-axis
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

        # Rolling 20-day return %
        fig2 = go.Figure()
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl].copy()
            d["rolling_ret"] = d["equity"].pct_change(20) * 100
            fig2.add_trace(go.Scatter(x=d["day"], y=d["rolling_ret"], name=lbl, mode="lines"))
        fig2.update_layout(title="Rolling 20-Day Return %",
                           yaxis_title="Return %", xaxis_title="Date", height=400)
        blocks.append(self._fig_html(fig2))

        # Daily P&L bar chart (waterfall style)
        for b in self.bundles:
            if b.daily.empty:
                continue
            d = b.daily.copy()
            colors = [_COLOR_WIN if v > 0 else _COLOR_LOSS for v in d["pnl"]]
            fig3 = go.Figure(go.Bar(x=d["day"], y=d["pnl"], marker_color=colors, name=b.label))
            fig3.update_layout(title=f"Daily P&L Bars – {b.label}", yaxis_title="P&L (INR)",
                               xaxis_title="Date", height=350)
            blocks.append(self._fig_html(fig3))

        # Cumulative P&L normalized to %
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

    # ---- 3. Calendar & Temporal -----------------------------------------------

    def _section_calendar(self, js: bool) -> Tuple[str, List[str]]:
        daily = self._cat("daily")
        blocks: List[str] = []
        if daily.empty:
            return "calendar", blocks

        # Calendar heatmap per run
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

        # Day of week performance
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

        # Monthly P&L heatmap (run × month)
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

        # Rolling win rate (20-day)
        fig4 = go.Figure()
        for lbl in daily["label"].unique():
            d = daily[daily["label"] == lbl].copy()
            d["win_flag"] = (d["pnl"] > 0).astype(float)
            d["rolling_wr"] = d["win_flag"].rolling(20, min_periods=5).mean() * 100
            fig4.add_trace(go.Scatter(x=d["day"], y=d["rolling_wr"], name=lbl, mode="lines"))
        fig4.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
        fig4.update_layout(title="Rolling 20-Day Win Rate %", yaxis_title="Win Rate %", height=400)
        blocks.append(self._fig_html(fig4))

        # Consecutive streak analysis
        for b in self.bundles:
            if b.daily.empty:
                continue
            d = b.daily.copy()
            streaks = []
            current = 0
            for pnl in d["pnl"]:
                if pnl > 0:
                    current = current + 1 if current > 0 else 1
                elif pnl < 0:
                    current = current - 1 if current < 0 else -1
                else:
                    current = 0
                streaks.append(current)
            d["streak"] = streaks
            colors = [_COLOR_WIN if v > 0 else _COLOR_LOSS if v < 0 else _COLOR_NEUTRAL for v in d["streak"]]
            fig5 = go.Figure(go.Bar(x=d["day"], y=d["streak"], marker_color=colors))
            fig5.update_layout(title=f"Consecutive Win/Loss Streaks – {b.label}",
                               yaxis_title="Streak Length", height=300)
            blocks.append(self._fig_html(fig5))

        return "calendar", blocks

    # ---- 4. Direction Alignment Matrix ----------------------------------------

    def _section_direction(self, js: bool) -> Tuple[str, List[str]]:
        merged = self._cat("merged")
        blocks: List[str] = []
        if merged.empty or "index_dir" not in merged.columns or "sector_dir" not in merged.columns:
            blocks.append("<p class='muted'>Direction matrix requires signal data merged with trades (nifty_pct, sector data).</p>")
            return "direction", blocks

        m = merged.dropna(subset=["index_dir", "sector_dir", "signal_dir"])
        if m.empty:
            return "direction", blocks

        # Overall direction matrix heatmap (P&L)
        combos = m.groupby(["label", "index_dir", "sector_dir", "signal_dir"], as_index=False).agg(
            trades=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            avg_pnl=("realized_pnl", "mean"),
        )
        combos["combo"] = combos["index_dir"] + " / " + combos["sector_dir"] + " / " + combos["signal_dir"]

        for lbl in combos["label"].unique():
            sub = combos[combos["label"] == lbl]
            # Build 2×2×2 matrix as a styled heatmap
            idx_order = ["UP", "DOWN"]
            sector_order = ["UP", "DOWN"]
            pnl_matrix = []
            wr_matrix = []
            trade_matrix = []
            y_labels = []
            for id_ in idx_order:
                for sd in sector_order:
                    y_labels.append(f"Idx:{id_} Sec:{sd}")
                    row_pnl = []
                    row_wr = []
                    row_tr = []
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
            fig.update_layout(title=f"Direction Alignment Matrix (Net P&L) – {lbl}", height=400)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

            # Win rate version
            fig_wr = go.Figure(go.Heatmap(
                z=wr_matrix, x=["Signal: UP (LONG)", "Signal: DOWN (SHORT)"],
                y=y_labels,
                colorscale=[[0, "#fca5a5"], [0.5, "#fefce8"], [1, "#86efac"]],
                zmid=50, colorbar_title="Win Rate %",
                hovertemplate="Win Rate: %{z:.1f}%<extra></extra>",
            ))
            fig_wr.update_layout(title=f"Direction Alignment Matrix (Win Rate %) – {lbl}", height=400)
            blocks.append(self._fig_html(fig_wr))

        # Alignment categories: Fully aligned, Partially, Counter-trend
        m_copy = m.copy()
        def _alignment(row):
            aligned = 0
            if row.get("index_dir") == row.get("signal_dir"):
                aligned += 1
            if row.get("sector_dir") == row.get("signal_dir"):
                aligned += 1
            if aligned == 2:
                return "Fully Aligned"
            elif aligned == 1:
                return "Partially Aligned"
            return "Counter-Trend"

        m_copy["alignment"] = m_copy.apply(_alignment, axis=1)
        align_perf = m_copy.groupby(["label", "alignment"], as_index=False).agg(
            trades=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            avg_pnl=("realized_pnl", "mean"),
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

        # Monthly direction alignment evolution
        if "entry_time" in m.columns:
            m_monthly = m.copy()
            m_monthly["month"] = m_monthly["entry_time"].dt.to_period("M").astype(str)
            m_monthly["alignment"] = m_monthly.apply(_alignment, axis=1)
            month_align = m_monthly.groupby(["label", "month", "alignment"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
            )
            for lbl in month_align["label"].unique():
                sub = month_align[month_align["label"] == lbl]
                fig_ma = px.bar(sub, x="month", y="net_pnl", color="alignment",
                                barmode="group",
                                title=f"Monthly Direction Alignment P&L – {lbl}")
                fig_ma.update_layout(height=400)
                blocks.append(self._fig_html(fig_ma))

        return "direction", blocks

    # ---- 5. Trade Deep Dive --------------------------------------------------

    def _section_trades(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "trades", blocks

        # MFE vs MAE scatter
        if "mfe_r" in trades.columns and "mae_r" in trades.columns:
            t = trades.dropna(subset=["mfe_r", "mae_r"])
            if not t.empty:
                t["outcome"] = np.where(t["realized_pnl"] > 0, "Win", "Loss")
                fig = px.scatter(t, x="mae_r", y="mfe_r", color="outcome",
                                 symbol="label" if t["label"].nunique() > 1 else None,
                                 color_discrete_map={"Win": _COLOR_WIN, "Loss": _COLOR_LOSS},
                                 opacity=0.5,
                                 hover_data=["symbol", "realized_pnl", "exit_reason"],
                                 title="MFE vs MAE (R-Multiples) – Trade Edge Analysis")
                fig.add_shape(type="line", x0=0, y0=0, x1=t["mae_r"].max(), y1=t["mae_r"].max(),
                              line=dict(dash="dash", color="gray"))
                fig.update_layout(xaxis_title="MAE (Adverse Excursion in R)",
                                  yaxis_title="MFE (Favorable Excursion in R)", height=500)
                blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # R-Multiple Distribution
        if "r_multiple" in trades.columns:
            t = trades.dropna(subset=["r_multiple"])
            if not t.empty:
                fig2 = px.histogram(t, x="r_multiple", color="label", barmode="overlay",
                                    nbins=60, opacity=0.7,
                                    title="R-Multiple Distribution")
                fig2.add_vline(x=0, line_dash="dash", line_color="black")
                fig2.update_layout(xaxis_title="R-Multiple", yaxis_title="Trade Count", height=400)
                blocks.append(self._fig_html(fig2))

        # Win/Loss P&L distribution (violin)
        trades_copy = trades.copy()
        trades_copy["outcome"] = np.where(trades_copy["realized_pnl"] > 0, "Win", "Loss")
        fig3 = px.violin(trades_copy, x="label", y="realized_pnl", color="outcome",
                          color_discrete_map={"Win": _COLOR_WIN, "Loss": _COLOR_LOSS},
                          box=True, points=False,
                          title="Win vs Loss P&L Distribution (Violin)")
        fig3.update_layout(height=450)
        blocks.append(self._fig_html(fig3))

        # Trade duration distribution
        if "duration_min" in trades.columns:
            fig4 = px.histogram(trades, x="duration_min", color="label", barmode="overlay",
                                nbins=50, opacity=0.7,
                                title="Trade Holding Period Distribution")
            fig4.update_layout(xaxis_title="Duration (minutes)", yaxis_title="Count", height=400)
            blocks.append(self._fig_html(fig4))

            # Duration vs P&L
            fig5 = px.scatter(trades, x="duration_min", y="realized_pnl", color="label",
                              opacity=0.4, title="Holding Period vs Realized P&L",
                              hover_data=["symbol", "exit_reason"])
            fig5.add_hline(y=0, line_dash="dash", line_color="gray")
            fig5.update_layout(xaxis_title="Duration (min)", yaxis_title="P&L (INR)", height=400)
            blocks.append(self._fig_html(fig5))

        # Exit reason analysis (treemap + performance)
        exit_perf = trades.groupby(["label", "exit_reason"], as_index=False).agg(
            trades_count=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
        )
        fig6 = make_subplots(rows=1, cols=3,
                              subplot_titles=("Net P&L by Exit Reason", "Avg P&L", "Win Rate %"))
        for lbl in exit_perf["label"].unique():
            sub = exit_perf[exit_perf["label"] == lbl]
            fig6.add_trace(go.Bar(x=sub["exit_reason"], y=sub["net_pnl"], name=lbl), row=1, col=1)
            fig6.add_trace(go.Bar(x=sub["exit_reason"], y=sub["avg_pnl"], name=lbl, showlegend=False), row=1, col=2)
            fig6.add_trace(go.Bar(x=sub["exit_reason"], y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=3)
        fig6.update_layout(title="Exit Reason Deep Dive", barmode="group", height=450)
        blocks.append(self._fig_html(fig6))

        # Exit reason sunburst (per run)
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

        # Grade performance (A+ vs A)
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
            fig_g.update_layout(title="Grade Performance (A+ vs A)", barmode="group", height=400)
            blocks.append(self._fig_html(fig_g))

        # Top 10 best & worst individual trades table
        for b in self.bundles:
            if b.trades.empty:
                continue
            best = b.trades.nlargest(10, "realized_pnl")[["symbol", "sector", "direction", "entry_time", "realized_pnl", "exit_reason"]]
            worst = b.trades.nsmallest(10, "realized_pnl")[["symbol", "sector", "direction", "entry_time", "realized_pnl", "exit_reason"]]
            def _trade_table(df, title):
                header = "<tr><th>Symbol</th><th>Sector</th><th>Dir</th><th>Entry</th><th>P&L</th><th>Exit</th></tr>"
                rows = ""
                for _, r in df.iterrows():
                    color = _COLOR_WIN if r["realized_pnl"] > 0 else _COLOR_LOSS
                    rows += f"<tr><td>{r['symbol']}</td><td>{r['sector']}</td><td>{r['direction']}</td>"
                    rows += f"<td>{r['entry_time']}</td><td style='color:{color};font-weight:bold'>₹{r['realized_pnl']:,.0f}</td>"
                    rows += f"<td>{r['exit_reason']}</td></tr>"
                return f"<h3>{title}</h3><table class='score-table'><thead>{header}</thead><tbody>{rows}</tbody></table>"
            blocks.append(f"<div style='display:flex;gap:24px;flex-wrap:wrap'>"
                          f"<div style='flex:1;min-width:400px'>{_trade_table(best, f'Top 10 Best Trades – {b.label}')}</div>"
                          f"<div style='flex:1;min-width:400px'>{_trade_table(worst, f'Top 10 Worst Trades – {b.label}')}</div></div>")

        return "trades", blocks

    # ---- 6. Regime & VIX Analysis --------------------------------------------

    def _section_regime(self, js: bool) -> Tuple[str, List[str]]:
        merged = self._cat("merged")
        blocks: List[str] = []
        if merged.empty:
            return "regime", blocks

        # Regime performance
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
            fig.update_layout(title="Regime Performance Breakdown", barmode="group", height=450)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

            # Regime × Direction
            if "direction" in merged.columns:
                rd = merged.groupby(["label", "regime", "direction"], as_index=False).agg(
                    net_pnl=("realized_pnl", "sum"),
                    win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                    trades=("realized_pnl", "size"),
                )
                for lbl in rd["label"].unique():
                    sub = rd[rd["label"] == lbl]
                    fig_rd = px.bar(sub, x="regime", y="net_pnl", color="direction",
                                    barmode="group",
                                    title=f"Regime × Direction P&L – {lbl}")
                    fig_rd.update_layout(height=400)
                    blocks.append(self._fig_html(fig_rd))

        # VIX bracket performance
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
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig_vb = make_subplots(rows=1, cols=2, subplot_titles=("Net P&L by VIX Bracket", "Win Rate %"))
            for lbl in vb["label"].unique():
                sub = vb[vb["label"] == lbl]
                fig_vb.add_trace(go.Bar(x=sub["vix_bracket"].astype(str), y=sub["net_pnl"], name=lbl), row=1, col=1)
                fig_vb.add_trace(go.Bar(x=sub["vix_bracket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig_vb.update_layout(title="VIX Bracket Performance", barmode="group", height=450)
            blocks.append(self._fig_html(fig_vb))

            # VIX percentile scatter vs P&L
            fig_vs = px.scatter(merged.dropna(subset=["vix_percentile"]),
                                x="vix_percentile", y="realized_pnl", color="label",
                                opacity=0.3, trendline="ols",
                                title="VIX Percentile vs Trade P&L (with regression)")
            fig_vs.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_vs.update_layout(xaxis_title="VIX Percentile", yaxis_title="P&L (INR)", height=450)
            blocks.append(self._fig_html(fig_vs))

        # Nifty % change vs P&L
        if "nifty_pct" in merged.columns:
            n = merged.dropna(subset=["nifty_pct"])
            if not n.empty:
                fig_np = px.scatter(n, x="nifty_pct", y="realized_pnl", color="label",
                                    opacity=0.3, trendline="ols",
                                    title="NIFTY % Change vs Trade P&L")
                fig_np.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_np.add_vline(x=0, line_dash="dash", line_color="gray")
                fig_np.update_layout(xaxis_title="NIFTY % Change", yaxis_title="P&L (INR)", height=450)
                blocks.append(self._fig_html(fig_np))

        # First trade effect analysis
        for b in self.bundles:
            if b.trades.empty:
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

    # ---- 7. Intraday Timing --------------------------------------------------

    def _section_timing(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty:
            return "timing", blocks

        # Entry time distribution
        if "entry_hhmm" in trades.columns:
            fig = px.histogram(trades, x="entry_hhmm", color="label", barmode="overlay",
                               opacity=0.7, title="Entry Time Distribution (HH:MM)")
            fig.update_layout(xaxis_title="Entry Time", yaxis_title="Trade Count", height=400)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Time bucket performance (comprehensive)
        bucket_perf = trades.groupby(["label", "entry_bucket"], as_index=False).agg(
            trades_count=("realized_pnl", "size"),
            net_pnl=("realized_pnl", "sum"),
            avg_pnl=("realized_pnl", "mean"),
            win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            total_wins=("win", "sum"),
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
        fig2.update_layout(title="Time Bucket Analysis (4 Metrics)", barmode="group", height=600)
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

    # ---- 8. Sector Analysis --------------------------------------------------

    def _section_sectors(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        blocks: List[str] = []
        if trades.empty or "sector" not in trades.columns:
            return "sectors", blocks

        # Sector performance heatmap (sector × metrics per run)
        for lbl in trades["label"].unique():
            sub = trades[trades["label"] == lbl]
            sp = sub.groupby("sector", as_index=False).agg(
                trades_count=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                total_notional=("notional_at_entry", "sum"),
            )
            sp = sp.sort_values("net_pnl", ascending=True)
            metrics = ["net_pnl", "avg_pnl", "win_rate", "trades_count"]
            z_data = []
            for m in metrics:
                vals = sp[m].values
                if vals.std() > 0:
                    z_data.append((vals - vals.mean()) / vals.std())  # z-score normalize
                else:
                    z_data.append(vals * 0)

            fig = go.Figure(go.Heatmap(
                z=np.array(z_data),
                x=sp["sector"].tolist(),
                y=["Net P&L", "Avg P&L", "Win Rate %", "Trade Count"],
                colorscale="RdYlGn", zmid=0,
                hovertemplate="Sector: %{x}<br>Metric: %{y}<br>Z-Score: %{z:.2f}<extra></extra>",
            ))
            fig.update_layout(title=f"Sector Performance Heatmap (Z-Score Normalized) – {lbl}",
                              height=350, xaxis_tickangle=45)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Sector P&L sorted bar
        sector_total = trades.groupby(["label", "sector"], as_index=False).agg(
            net_pnl=("realized_pnl", "sum"),
        )
        sector_sort = sector_total.groupby("sector")["net_pnl"].sum().sort_values()
        sector_order = sector_sort.index.tolist()
        sector_total["sector"] = pd.Categorical(sector_total["sector"], categories=sector_order, ordered=True)
        fig2 = px.bar(sector_total.sort_values("sector"), x="net_pnl", y="sector", color="label",
                       barmode="group", orientation="h",
                       title="Sector Net P&L (Sorted)")
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
            st["abs_pnl"] = st["net_pnl"].abs()
            fig_tm = px.treemap(st, path=["sector"], values="trades_count", color="net_pnl",
                                color_continuous_scale=[[0, _COLOR_LOSS], [0.5, "#fefce8"], [1, _COLOR_WIN]],
                                color_continuous_midpoint=0,
                                title=f"Sector Treemap (size=trades, color=P&L) – {b.label}")
            fig_tm.update_layout(height=500)
            blocks.append(self._fig_html(fig_tm))

        # Sector × Direction
        if "direction" in trades.columns:
            sd = trades.groupby(["label", "sector", "direction"], as_index=False).agg(
                net_pnl=("realized_pnl", "sum"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                trades_count=("realized_pnl", "size"),
            )
            for lbl in sd["label"].unique():
                sub = sd[sd["label"] == lbl]
                top_sectors = sub.groupby("sector")["trades_count"].sum().nlargest(10).index.tolist()
                sub = sub[sub["sector"].isin(top_sectors)]
                fig_sd = px.bar(sub, x="sector", y="net_pnl", color="direction",
                                barmode="group",
                                title=f"Sector × Direction P&L (Top 10 Sectors) – {lbl}")
                fig_sd.update_layout(height=400, xaxis_tickangle=45)
                blocks.append(self._fig_html(fig_sd))

        # Sector P&L evolution over months
        if "entry_time" in trades.columns:
            trades_m = trades.copy()
            trades_m["month"] = trades_m["entry_time"].dt.to_period("M").astype(str)
            top_sectors_all = trades_m.groupby("sector")["realized_pnl"].count().nlargest(8).index.tolist()
            sm = trades_m[trades_m["sector"].isin(top_sectors_all)].groupby(
                ["label", "month", "sector"], as_index=False
            )["realized_pnl"].sum()
            for lbl in sm["label"].unique():
                sub = sm[sm["label"] == lbl]
                fig_se = px.line(sub, x="month", y="realized_pnl", color="sector",
                                 title=f"Sector Monthly P&L Evolution (Top 8) – {lbl}")
                fig_se.update_layout(height=400)
                blocks.append(self._fig_html(fig_se))

        return "sectors", blocks

    # ---- 9. Signal Quality & Indicators --------------------------------------

    def _section_signals(self, js: bool) -> Tuple[str, List[str]]:
        merged = self._cat("merged")
        signals = self._cat("signals")
        blocks: List[str] = []

        # Score vs P&L scatter
        if not merged.empty and "score" in merged.columns:
            m = merged.dropna(subset=["score"])
            if not m.empty:
                fig = px.scatter(m, x="score", y="realized_pnl", color="label",
                                 opacity=0.3, trendline="ols",
                                 title="Signal Score vs Realized P&L")
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.update_layout(height=450)
                blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Score distribution: Executed vs Rejected
        if not signals.empty and "score" in signals.columns:
            sig = signals.copy()
            sig["executed"] = sig.get("executed_trade", False).fillna(False)
            sig["status"] = np.where(sig["executed"], "Executed", "Rejected")
            fig2 = px.histogram(sig, x="score", color="status", barmode="overlay",
                                opacity=0.6, nbins=30,
                                color_discrete_map={"Executed": "#3b82f6", "Rejected": "#94a3b8"},
                                title="Signal Score Distribution: Executed vs Rejected")
            fig2.update_layout(height=400)
            blocks.append(self._fig_html(fig2))

        # RVOL bucket performance
        if not merged.empty and "rvol" in merged.columns:
            m = merged.dropna(subset=["rvol"]).copy()
            m["rvol_bucket"] = pd.cut(m["rvol"], bins=[0, 1.3, 1.7, 2.5, 5, 100],
                                       labels=["<1.3", "1.3-1.7", "1.7-2.5", "2.5-5.0", "5.0+"],
                                       include_lowest=True)
            rb = m.groupby(["label", "rvol_bucket"], observed=True).agg(
                trades=("realized_pnl", "size"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig3 = make_subplots(rows=1, cols=2, subplot_titles=("Avg P&L by RVOL", "Win Rate %"))
            for lbl in rb["label"].unique():
                sub = rb[rb["label"] == lbl]
                fig3.add_trace(go.Bar(x=sub["rvol_bucket"].astype(str), y=sub["avg_pnl"], name=lbl), row=1, col=1)
                fig3.add_trace(go.Bar(x=sub["rvol_bucket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig3.update_layout(title="RVOL Bracket Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig3))

        # StochK bucket performance
        if not merged.empty and "stoch_k" in merged.columns:
            m = merged.dropna(subset=["stoch_k"]).copy()
            m["stoch_bucket"] = pd.cut(m["stoch_k"], bins=[0, 20, 40, 60, 80, 100],
                                        labels=["0-20", "20-40", "40-60", "60-80", "80-100"],
                                        include_lowest=True)
            sb = m.groupby(["label", "stoch_bucket"], observed=True).agg(
                trades=("realized_pnl", "size"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig4 = make_subplots(rows=1, cols=2, subplot_titles=("Avg P&L by StochK", "Win Rate %"))
            for lbl in sb["label"].unique():
                sub = sb[sb["label"] == lbl]
                fig4.add_trace(go.Bar(x=sub["stoch_bucket"].astype(str), y=sub["avg_pnl"], name=lbl), row=1, col=1)
                fig4.add_trace(go.Bar(x=sub["stoch_bucket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig4.update_layout(title="Stochastic K Bracket Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig4))

        # Sector rank vs performance
        if not merged.empty and "sector_rank" in merged.columns:
            m = merged.dropna(subset=["sector_rank"]).copy()
            m["sector_rank"] = m["sector_rank"].astype(int)
            srp = m.groupby(["label", "sector_rank"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
                net_pnl=("realized_pnl", "sum"),
            )
            srp = srp.sort_values("sector_rank")
            fig5 = make_subplots(rows=1, cols=2, subplot_titles=("Net P&L by Sector Rank", "Win Rate %"))
            for lbl in srp["label"].unique():
                sub = srp[srp["label"] == lbl]
                fig5.add_trace(go.Bar(x=sub["sector_rank"].astype(str), y=sub["net_pnl"], name=lbl), row=1, col=1)
                fig5.add_trace(go.Bar(x=sub["sector_rank"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig5.update_layout(title="Sector Rank Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig5))

        # Spread ATR vs performance
        if not merged.empty and "spread_atr" in merged.columns:
            m = merged.dropna(subset=["spread_atr"]).copy()
            m["spread_bucket"] = pd.cut(m["spread_atr"], bins=[0, 0.02, 0.05, 0.1, 0.25, 1.0],
                                         labels=["<0.02", "0.02-0.05", "0.05-0.10", "0.10-0.25", "0.25+"],
                                         include_lowest=True)
            sp = m.groupby(["label", "spread_bucket"], observed=True).agg(
                trades=("realized_pnl", "size"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig6 = make_subplots(rows=1, cols=2, subplot_titles=("Avg P&L by Spread/ATR", "Win Rate %"))
            for lbl in sp["label"].unique():
                sub = sp[sp["label"] == lbl]
                fig6.add_trace(go.Bar(x=sub["spread_bucket"].astype(str), y=sub["avg_pnl"], name=lbl), row=1, col=1)
                fig6.add_trace(go.Bar(x=sub["spread_bucket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig6.update_layout(title="Spread/ATR Bracket Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig6))

        # ADV bucket performance
        if not merged.empty and "adv_crores" in merged.columns:
            m = merged.dropna(subset=["adv_crores"]).copy()
            m["adv_bucket"] = pd.cut(m["adv_crores"], bins=[0, 100, 250, 500, 1000, 100000],
                                      labels=["<100Cr", "100-250Cr", "250-500Cr", "500-1000Cr", "1000Cr+"],
                                      include_lowest=True)
            ap = m.groupby(["label", "adv_bucket"], observed=True).agg(
                trades=("realized_pnl", "size"),
                avg_pnl=("realized_pnl", "mean"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            ).reset_index()
            fig7 = make_subplots(rows=1, cols=2, subplot_titles=("Avg P&L by ADV", "Win Rate %"))
            for lbl in ap["label"].unique():
                sub = ap[ap["label"] == lbl]
                fig7.add_trace(go.Bar(x=sub["adv_bucket"].astype(str), y=sub["avg_pnl"], name=lbl), row=1, col=1)
                fig7.add_trace(go.Bar(x=sub["adv_bucket"].astype(str), y=sub["win_rate"], name=lbl, showlegend=False), row=1, col=2)
            fig7.update_layout(title="ADV (Average Daily Volume) Bracket Performance", barmode="group", height=400)
            blocks.append(self._fig_html(fig7))

        # HMA alignment performance
        if not merged.empty and "hma_align" in merged.columns:
            hma = merged.groupby(["label", "hma_align"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                win_rate=("win", lambda s: round(s.mean() * 100, 1)),
            )
            fig8 = px.bar(hma, x="hma_align", y="net_pnl", color="label",
                           barmode="group", title="HMA Alignment Performance")
            fig8.update_layout(height=400)
            blocks.append(self._fig_html(fig8))

        return "signals", blocks

    # ---- 10. Execution Funnel ------------------------------------------------

    def _section_funnel(self, js: bool) -> Tuple[str, List[str]]:
        blocks: List[str] = []

        for b in self.bundles:
            summary = b.summary
            all_sigs = int(summary.get("all_signals", 0))
            executed = int(summary.get("executed_signals", 0))
            wins = int(summary.get("wins", 0))
            losses = int(summary.get("losses", 0))

            # Gate pass count from signals
            gate_pass = 0
            if not b.signals.empty and "gate_passed" in b.signals.columns:
                gate_pass = int(b.signals["gate_passed"].sum())
            else:
                gate_pass = all_sigs  # fallback

            # Risk pass from signals
            risk_pass = 0
            if not b.signals.empty and "risk_allowed" in b.signals.columns:
                risk_pass = int(b.signals["risk_allowed"].sum())
            else:
                risk_pass = executed

            stages = ["All A/A+ Signals", "Gate Passed", "Risk Approved", "Executed", "Profitable"]
            values = [all_sigs, gate_pass, risk_pass, executed, wins]

            fig = go.Figure(go.Funnel(
                y=stages, x=values,
                textposition="inside",
                textinfo="value+percent initial",
                marker=dict(color=["#3b82f6", "#8b5cf6", "#f59e0b", "#22c55e", "#10b981"]),
            ))
            fig.update_layout(title=f"Execution Funnel – {b.label}", height=450)
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Decision breakdown (stacked bar)
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

        # Position capacity utilization over time
        for b in self.bundles:
            if b.daily.empty or b.trades.empty:
                continue
            d = b.daily.copy()
            # Estimate peak concurrent positions by counting overlapping trades per day
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
            fig4.update_layout(title=f"Daily Trade Count vs Max Position Limit – {b.label}",
                               yaxis_title="Trade Count", height=350)
            blocks.append(self._fig_html(fig4))

        return "funnel", blocks

    # ---- 11. Risk & Position Sizing ------------------------------------------

    def _section_risk(self, js: bool) -> Tuple[str, List[str]]:
        trades = self._cat("trades")
        merged = self._cat("merged")
        positions = self._cat("positions")
        blocks: List[str] = []
        if trades.empty:
            return "risk", blocks

        # Risk per trade distribution
        if "entry_risk_per_share" in trades.columns and "initial_qty" in trades.columns:
            t = trades.copy()
            t["trade_risk"] = (t["entry_risk_per_share"] * t["initial_qty"]).abs()
            t = t.dropna(subset=["trade_risk"])
            if not t.empty:
                fig = px.histogram(t, x="trade_risk", color="label", barmode="overlay",
                                   nbins=40, opacity=0.7,
                                   title="Total Risk Per Trade Distribution (INR)")
                fig.update_layout(xaxis_title="Risk Amount (INR)", height=400)
                blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Notional at entry distribution
        if "notional_at_entry" in trades.columns:
            t = trades.dropna(subset=["notional_at_entry"])
            if not t.empty:
                fig2 = px.histogram(t, x="notional_at_entry", color="label", barmode="overlay",
                                    nbins=40, opacity=0.7,
                                    title="Notional at Entry Distribution")
                fig2.update_layout(xaxis_title="Notional (INR)", height=400)
                blocks.append(self._fig_html(fig2))

        # Notional vs P&L scatter
        if "notional_at_entry" in trades.columns:
            fig3 = px.scatter(trades.dropna(subset=["notional_at_entry"]),
                              x="notional_at_entry", y="realized_pnl", color="label",
                              opacity=0.3, title="Notional at Entry vs P&L")
            fig3.add_hline(y=0, line_dash="dash", line_color="gray")
            fig3.update_layout(xaxis_title="Notional (INR)", yaxis_title="P&L (INR)", height=400)
            blocks.append(self._fig_html(fig3))

        # Effective risk % distribution (from positions)
        if not positions.empty and "effective_risk_pct" in positions.columns:
            ep = positions[positions.get("executed_trade", False) == True] if "executed_trade" in positions.columns else positions
            if not ep.empty and "effective_risk_pct" in ep.columns:
                fig4 = px.histogram(ep.dropna(subset=["effective_risk_pct"]),
                                    x="effective_risk_pct", color="label",
                                    barmode="overlay", nbins=30, opacity=0.7,
                                    title="Effective Risk % Distribution (Executed Trades)")
                fig4.update_layout(xaxis_title="Effective Risk %", height=400)
                blocks.append(self._fig_html(fig4))

        # Sector concentration (notional)
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

    # ---- 12. Parameter Optimization ------------------------------------------

    def _section_params(self, js: bool) -> Tuple[str, List[str]]:
        sdf = self.summary_df
        blocks: List[str] = []
        if sdf.empty or len(sdf) < 2:
            blocks.append("<p class='muted'>Parameter optimization requires 2+ runs for comparison.</p>")
            return "params", blocks

        # Parameter impact matrix (correlation with metrics)
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
                colorscale="RdBu_r", zmid=0,
                colorbar_title="Correlation",
                hovertemplate="Param: %{y}<br>Metric: %{x}<br>Corr: %{z:.3f}<extra></extra>",
            ))
            fig.update_layout(title="Parameter × Metric Correlation Matrix",
                              height=max(300, len(pdf) * 25 + 100))
            blocks.append(self._fig_html(fig, js=(js and len(blocks) == 0)))

        # Individual parameter vs return (faceted scatter)
        rows: List[Dict[str, Any]] = []
        for pk in PARAM_KEYS:
            if pk not in sdf.columns:
                continue
            vals = pd.to_numeric(sdf[pk], errors="coerce")
            if vals.notna().sum() < 2 or vals.nunique(dropna=True) < 2:
                continue
            for _, r in sdf.iterrows():
                x = float(vals[r.name]) if pd.notna(vals[r.name]) else float("nan")
                if pd.isna(x):
                    continue
                rows.append({
                    "label": r["label"], "parameter": pk,
                    "value": x,
                    "total_return_pct": _f(r.get("total_return_pct")),
                    "win_rate_pct": _f(r.get("win_rate_pct")),
                    "max_dd_pct": _f(r.get("max_dd_pct")),
                })

        if rows:
            psd = pd.DataFrame(rows)
            # Top variable parameters
            top_var = (psd.groupby("parameter")["value"].nunique()
                       .sort_values(ascending=False).head(9).index.tolist())
            sub = psd[psd["parameter"].isin(top_var)]
            if not sub.empty:
                fig2 = px.scatter(sub, x="value", y="total_return_pct", color="label",
                                   facet_col="parameter", facet_col_wrap=3,
                                   title="Parameter Value vs Return % (Top Variable Params)")
                fig2.update_layout(height=max(450, (len(top_var) // 3 + 1) * 350))
                blocks.append(self._fig_html(fig2))

        # Scoring weight analysis (radar)
        scoring_params = ["POINTS_HMA", "POINTS_RVOL", "POINTS_STOCH",
                          "POINTS_SECTOR_RANK", "POINTS_SPREAD"]
        scoring_avail = [p for p in scoring_params if p in sdf.columns]
        if len(scoring_avail) >= 3:
            fig3 = go.Figure()
            for _, r in sdf.iterrows():
                vals = [_f(r.get(p)) for p in scoring_avail]
                fig3.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=[p.replace("POINTS_", "") for p in scoring_avail] + [scoring_avail[0].replace("POINTS_", "")],
                    name=r["label"], fill="toself", opacity=0.5,
                ))
            fig3.update_layout(title="Scoring Weight Configuration Comparison",
                               polar=dict(radialaxis=dict(visible=True)), height=450)
            blocks.append(self._fig_html(fig3))

        # VIX multiplier comparison
        vix_params = ["VIX_MULT_LOW", "VIX_MULT_NORMAL", "VIX_MULT_ELEVATED",
                      "VIX_MULT_HIGH", "VIX_MULT_EXTREME"]
        vix_avail = [p for p in vix_params if p in sdf.columns]
        if len(vix_avail) >= 3:
            vix_rows = []
            for _, r in sdf.iterrows():
                for p in vix_avail:
                    vix_rows.append({
                        "label": r["label"],
                        "bracket": p.replace("VIX_MULT_", ""),
                        "multiplier": _f(r.get(p)),
                    })
            vdf = pd.DataFrame(vix_rows)
            fig4 = px.bar(vdf, x="bracket", y="multiplier", color="label",
                           barmode="group", title="VIX Multiplier Configuration Comparison")
            fig4.update_layout(height=400)
            blocks.append(self._fig_html(fig4))

        # Stop/Target/Trail config comparison
        st_params = ["STOP_ATR_MULT", "TARGET_1_MULT", "TARGET_1_EXIT_PCT",
                     "CHANDELIER_ATR_MULT", "CHANDELIER_LOOKBACK"]
        st_avail = [p for p in st_params if p in sdf.columns and sdf[p].notna().any()]
        if st_avail:
            st_rows = []
            for _, r in sdf.iterrows():
                for p in st_avail:
                    st_rows.append({"label": r["label"], "param": p, "value": _f(r.get(p))})
            stdf = pd.DataFrame(st_rows)
            fig5 = px.bar(stdf, x="param", y="value", color="label",
                           barmode="group", title="Stop/Target/Trail Configuration")
            fig5.update_layout(height=400, xaxis_tickangle=25)
            blocks.append(self._fig_html(fig5))

        # Sector weight comparison
        sw_params = [p for p in PARAM_KEYS if p.startswith("SECTOR_WEIGHTS.")]
        sw_avail = [p for p in sw_params if p in sdf.columns and sdf[p].notna().any()]
        if sw_avail:
            sw_rows = []
            for _, r in sdf.iterrows():
                for p in sw_avail:
                    sw_rows.append({
                        "label": r["label"],
                        "weight": p.replace("SECTOR_WEIGHTS.", ""),
                        "value": _f(r.get(p)),
                    })
            swdf = pd.DataFrame(sw_rows)
            fig6 = px.bar(swdf, x="weight", y="value", color="label",
                           barmode="group", title="Sector Scoring Weight Configuration")
            fig6.update_layout(height=400)
            blocks.append(self._fig_html(fig6))

        return "params", blocks

    # ══════════════════════════════════════════════════════════════════════════
    # HTML Builder
    # ══════════════════════════════════════════════════════════════════════════

    def build_html(self, output_path: Path,
                   title: str = "V6 PRO Backtest Graph Analysis") -> Path:
        builder_map = {
            "summary":   self._section_summary,
            "equity":    self._section_equity,
            "calendar":  self._section_calendar,
            "direction": self._section_direction,
            "trades":    self._section_trades,
            "regime":    self._section_regime,
            "timing":    self._section_timing,
            "sectors":   self._section_sectors,
            "signals":   self._section_signals,
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

        # Build navigation
        nav_links = "".join(
            f'<a href="#{sid}" class="nav-link">{stitle}</a>'
            for sid, stitle, blocks in all_blocks if blocks
        )

        # Build sections
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
    <span class="brand">V6 PRO Dashboard</span>
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
    p = argparse.ArgumentParser(description="V6 PRO Graph Analyzer")
    p.add_argument("history_files", nargs="*", help="Explicit history JSON file paths")
    p.add_argument("--labels", nargs="*", help="Labels (same order as files)")
    p.add_argument("--output", default="", help="Output HTML path")
    p.add_argument("--title", default="V6 PRO Backtest Graph Analysis")
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
    output = Path(args.output) if args.output else (ROOT / "analysis" / f"pro_graph_analysis_{stamp}.html")

    print(f"Loading {len(all_files)} history files ...")
    analyzer = ProGraphAnalyzer(all_files, labels=labels)
    analyzer.load()

    print("Building dashboard ...")
    out = analyzer.build_html(output_path=output, title=args.title)

    print(f"\nDashboard exported: {out}")
    print(f"Runs analyzed: {len(analyzer.bundles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
