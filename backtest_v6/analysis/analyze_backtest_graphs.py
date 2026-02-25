"""
V6 Graph-Based Backtest Analyzer

Generates a rich HTML dashboard across one or many backtest history files.

Highlights:
- Multi-file comparison with clear run labels
- Equity, drawdown, daily journey, regime/time-bucket/sector views
- Execution funnel and rejection reason analysis
- Parameter-sensitivity charts for config optimization
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit(
        "plotly is required for graph analysis. Install it with: pip install plotly"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_SOURCES = [
    # Each item supports:
    # - a directory path (latest backtest_history_*.json from that directory is selected), or
    # - a direct JSON file path (that exact file is selected)
    # You can freely mix both styles.
    # {"path": ROOT / "history", "label": "v6.0"},
    # {"path": ROOT / "history_v6.1", "label": "v6.1"},
    {"path": ROOT / "history_v6.2" / "backtest_history_24-02-2026_08-33_am.json", "label": "v6.2_run1"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_07-30_am.json", "label": "v6.2_run2"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_09-11_am.json", "label": "v6.2_run3"},
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_10-58_am.json", "label": "v6.2_run4"},
    {"path": ROOT / "history_v6.4" / "backtest_history_24-02-2026_04-09_pm.json", "label": "v6.4"},
    # {"path": ROOT / "history_v6.3", "label": "v6.3"},
    # {"path": ROOT / "history_v6.4", "label": "v6.4"},
    # Example pinned files:
    # {"path": ROOT / "history_v6.2" / "backtest_history_25-02-2026_10-58_am.json", "label": "v6.2_best"},
]


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _pct(n: float, d: float) -> float:
    return (n / d * 100.0) if d else 0.0


def _normalize_reason(text: Any) -> str:
    s = str(text or "NA")
    if "(" in s:
        s = s.split("(", 1)[0].strip()
    return s


def _safe_label_from_path(path: Path) -> str:
    m = re.search(
        r"backtest_history_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}_(?:am|pm))",
        path.name,
        re.IGNORECASE,
    )
    return m.group(1) if m else path.stem


@dataclass
class RunBundle:
    label: str
    history_path: Path
    raw: Dict[str, Any]
    summary_row: Dict[str, Any]
    daily_df: pd.DataFrame
    trades_df: pd.DataFrame
    signals_df: pd.DataFrame
    all_positions_df: pd.DataFrame


class GraphAnalyzer:
    PARAM_KEYS = [
        "BASE_RISK_PER_TRADE_PCT",
        "MAX_CONCURRENT_POSITIONS",
        "MAX_POSITIONS_PER_SECTOR",
        "MAX_POSITIONS_PER_STOCK",
        "STOP_ATR_MULT",
        "TARGET_1_MULT",
        "TARGET_1_EXIT_PCT",
        "CHANDELIER_ATR_MULT",
        "CHANDELIER_LOOKBACK",
        "RISK_MULT_LUNCH",
        "RISK_MULT_WARNING",
        "MIN_ADV_CRORES",
        "SPREAD_ATR_LIMIT",
        "THRESHOLD_A_PLUS",
        "THRESHOLD_A",
        "THRESHOLD_B",
        "POINTS_HMA",
        "POINTS_RVOL",
        "POINTS_STOCH",
        "POINTS_SECTOR_RANK",
        "POINTS_SPREAD",
        "VIX_MULT_LOW",
        "VIX_MULT_NORMAL",
        "VIX_MULT_ELEVATED",
        "VIX_MULT_HIGH",
        "VIX_MULT_EXTREME",
        "SECTOR_WEIGHTS.structural",
        "SECTOR_WEIGHTS.shortterm",
        "SECTOR_WEIGHTS.intraday",
        "SECTOR_WEIGHTS.breadth",
        "SECTOR_WEIGHTS.nifty",
    ]

    def __init__(self, history_files: Sequence[Path], labels: Optional[Sequence[str]] = None):
        if labels and len(labels) != len(history_files):
            raise ValueError("--labels must match the number of history files")
        self.files = list(history_files)
        self.labels = list(labels) if labels else []
        self.bundles: List[RunBundle] = []

    @staticmethod
    def _extract_param(config: Dict[str, Any], key: str) -> Optional[float]:
        if "." in key:
            base, sub = key.split(".", 1)
            val = (config.get(base) or {}).get(sub)
        else:
            val = config.get(key)
        try:
            if val is None:
                return None
            return float(val)
        except (TypeError, ValueError):
            return None

    def _load_one(self, history_path: Path, label: str) -> RunBundle:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        run = data.get("run", {})
        summary = data.get("summary", {})
        config = data.get("config_snapshot", {})
        decision_counts = summary.get("decision_counts", {}) or {}
        risk_reason_counts = summary.get("risk_reason_counts", {}) or {}

        daily_df = pd.DataFrame(data.get("daily_results", []))
        if not daily_df.empty:
            daily_df["day"] = pd.to_datetime(daily_df.get("day"), errors="coerce")
            daily_df["pnl"] = pd.to_numeric(daily_df.get("pnl"), errors="coerce").fillna(0.0)
            daily_df["start_equity"] = pd.to_numeric(daily_df.get("start_equity"), errors="coerce")
            daily_df["end_equity"] = pd.to_numeric(daily_df.get("end_equity"), errors="coerce")
            daily_df = daily_df.sort_values("day")
            if daily_df["start_equity"].notna().any():
                initial = float(daily_df["start_equity"].dropna().iloc[0])
            else:
                initial = _to_float(summary.get("initial_equity", 0.0))
            daily_df["equity_curve"] = initial + daily_df["pnl"].cumsum()
            daily_df["peak_equity"] = daily_df["equity_curve"].cummax()
            daily_df["drawdown"] = daily_df["equity_curve"] - daily_df["peak_equity"]
            daily_df["drawdown_pct"] = np.where(
                daily_df["peak_equity"] > 0,
                (daily_df["equity_curve"] / daily_df["peak_equity"] - 1.0) * 100.0,
                np.nan,
            )
            daily_df["month"] = daily_df["day"].dt.to_period("M").astype(str)
            daily_df["label"] = label

        trades_df = pd.DataFrame(data.get("trade_records", []))
        if not trades_df.empty:
            trades_df["entry_time"] = pd.to_datetime(trades_df.get("entry_time"), errors="coerce")
            trades_df["exit_time"] = pd.to_datetime(trades_df.get("exit_time"), errors="coerce")
            trades_df["realized_pnl"] = pd.to_numeric(trades_df.get("realized_pnl"), errors="coerce").fillna(0.0)
            trades_df["entry_price"] = pd.to_numeric(trades_df.get("entry_price"), errors="coerce").fillna(0.0)
            trades_df["initial_qty"] = pd.to_numeric(trades_df.get("initial_qty"), errors="coerce").fillna(0)
            trades_df["entry_notional"] = trades_df["entry_price"] * trades_df["initial_qty"]
            trades_df["entry_hour"] = trades_df["entry_time"].dt.hour
            trades_df["entry_bucket"] = pd.cut(
                trades_df["entry_hour"].fillna(-1),
                bins=[-1, 10, 12, 13, 14, 16],
                labels=["OPEN", "MID", "LUNCH", "AFTERNOON", "LATE"],
                include_lowest=True,
            ).astype(str)
            trades_df["label"] = label

        signals_df = pd.DataFrame(data.get("all_signal_records", []))
        if not signals_df.empty:
            signals_df["label"] = label
            for col in ["score", "rvol", "stoch_k", "vix_percentile", "nifty_pct", "change_pct", "adv_crores"]:
                if col in signals_df.columns:
                    signals_df[col] = pd.to_numeric(signals_df[col], errors="coerce")

        all_positions_df = pd.DataFrame(data.get("all_position_records", []))
        if not all_positions_df.empty:
            all_positions_df["label"] = label

        wins = int((trades_df.get("realized_pnl", pd.Series(dtype=float)) > 0).sum()) if not trades_df.empty else 0
        losses = int((trades_df.get("realized_pnl", pd.Series(dtype=float)) < 0).sum()) if not trades_df.empty else 0
        gross_profit = float(trades_df.loc[trades_df.get("realized_pnl", pd.Series(dtype=float)) > 0, "realized_pnl"].sum()) if not trades_df.empty else 0.0
        gross_loss = float(trades_df.loc[trades_df.get("realized_pnl", pd.Series(dtype=float)) < 0, "realized_pnl"].sum()) if not trades_df.empty else 0.0
        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else np.nan

        row: Dict[str, Any] = {
            "label": label,
            "history_file": str(history_path),
            "run_id": run.get("run_id", ""),
            "status": run.get("status", ""),
            "start_date": run.get("start_date", ""),
            "end_date": run.get("end_date", ""),
            "initial_equity": _to_float(summary.get("initial_equity", 0.0)),
            "final_equity": _to_float(summary.get("final_equity", 0.0)),
            "total_return": _to_float(summary.get("total_return", 0.0)),
            "total_return_pct": _to_float(summary.get("total_return_pct", 0.0)),
            "trading_days": int(_to_float(summary.get("trading_days", 0))),
            "closed_trades": int(_to_float(summary.get("closed_trades", len(trades_df)))),
            "all_signals": int(_to_float(summary.get("all_a_grade_signals", len(signals_df)))),
            "executed_signals": int(_to_float(summary.get("executed_positions", len(trades_df)))),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(_pct(wins, max(1, wins + losses)), 2),
            "profit_factor": float(profit_factor) if pd.notna(profit_factor) else np.nan,
            "avg_trade_pnl": float(trades_df["realized_pnl"].mean()) if not trades_df.empty else np.nan,
            "best_trade": float(trades_df["realized_pnl"].max()) if not trades_df.empty else np.nan,
            "worst_trade": float(trades_df["realized_pnl"].min()) if not trades_df.empty else np.nan,
            "capital_blocked_count": int(_to_float(summary.get("capital_blocked_count", 0))),
            "max_positions_blocked": int(_to_float(summary.get("blocked_by_max_positions_count", 0))),
            "execution_rate_pct": round(
                _pct(
                    _to_float(summary.get("executed_positions", len(trades_df))),
                    _to_float(summary.get("all_position_candidates", len(signals_df))),
                ),
                2,
            ),
            "decision_counts": decision_counts,
            "risk_reason_counts": risk_reason_counts,
        }

        if not daily_df.empty:
            row["max_drawdown_inr"] = float((-daily_df["drawdown"]).max())
            row["max_drawdown_pct"] = float((-daily_df["drawdown_pct"]).max())
            row["avg_daily_pnl"] = float(daily_df["pnl"].mean())
            row["positive_days"] = int((daily_df["pnl"] > 0).sum())
            row["negative_days"] = int((daily_df["pnl"] < 0).sum())

        for k in self.PARAM_KEYS:
            row[k] = self._extract_param(config, k)

        return RunBundle(
            label=label,
            history_path=history_path,
            raw=data,
            summary_row=row,
            daily_df=daily_df,
            trades_df=trades_df,
            signals_df=signals_df,
            all_positions_df=all_positions_df,
        )

    def load(self) -> None:
        self.bundles.clear()
        for i, fp in enumerate(self.files):
            label = self.labels[i] if self.labels else _safe_label_from_path(fp)
            self.bundles.append(self._load_one(fp, label))

    @property
    def summary_df(self) -> pd.DataFrame:
        return pd.DataFrame([b.summary_row for b in self.bundles])

    def _concat(self, attr: str) -> pd.DataFrame:
        frames = [getattr(b, attr) for b in self.bundles if not getattr(b, attr).empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _decision_breakdown_df(self) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for b in self.bundles:
            dc = b.summary_row.get("decision_counts") or {}
            for k, v in dc.items():
                rows.append({"label": b.label, "reason": _normalize_reason(k), "count": int(v)})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        totals = df.groupby("reason", as_index=False)["count"].sum().sort_values("count", ascending=False)
        top = set(totals.head(12)["reason"].tolist())
        df["reason"] = np.where(df["reason"].isin(top), df["reason"], "OTHER")
        return df.groupby(["label", "reason"], as_index=False)["count"].sum()

    def _risk_breakdown_df(self) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for b in self.bundles:
            rc = b.summary_row.get("risk_reason_counts") or {}
            for k, v in rc.items():
                rows.append({"label": b.label, "reason": _normalize_reason(k), "count": int(v)})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        totals = df.groupby("reason", as_index=False)["count"].sum().sort_values("count", ascending=False)
        top = set(totals.head(12)["reason"].tolist())
        df["reason"] = np.where(df["reason"].isin(top), df["reason"], "OTHER")
        return df.groupby(["label", "reason"], as_index=False)["count"].sum()

    def _param_sensitivity_df(self, summary_df: pd.DataFrame) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        if summary_df.empty:
            return pd.DataFrame()
        for param in self.PARAM_KEYS:
            if param not in summary_df.columns:
                continue
            vals = pd.to_numeric(summary_df[param], errors="coerce")
            if vals.notna().sum() < 2 or vals.nunique(dropna=True) < 2:
                continue
            for _, r in summary_df.iterrows():
                x = pd.to_numeric(pd.Series([r.get(param)]), errors="coerce").iloc[0]
                if pd.isna(x):
                    continue
                rows.append(
                    {
                        "label": r["label"],
                        "parameter": param,
                        "value": float(x),
                        "total_return_pct": float(r.get("total_return_pct", np.nan)),
                        "win_rate_pct": float(r.get("win_rate_pct", np.nan)),
                        "max_drawdown_pct": float(r.get("max_drawdown_pct", np.nan)),
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def _fig_to_html(fig: go.Figure, include_js: bool = False) -> str:
        return fig.to_html(full_html=False, include_plotlyjs=("cdn" if include_js else False), config={"displaylogo": False})

    def build_html(self, output_path: Path, title: str = "V6 Backtest Graph Analysis") -> Path:
        summary_df = self.summary_df
        daily_df = self._concat("daily_df")
        trades_df = self._concat("trades_df")
        signals_df = self._concat("signals_df")

        if summary_df.empty:
            raise ValueError("No valid backtest data to analyze")

        figures: List[go.Figure] = []

        if not daily_df.empty:
            figures.append(
                px.line(
                    daily_df,
                    x="day",
                    y="equity_curve",
                    color="label",
                    title="Equity Curve Comparison (Daily Journey)",
                    labels={"equity_curve": "Equity (INR)", "day": "Date", "label": "Run"},
                )
            )

            figures.append(
                px.line(
                    daily_df,
                    x="day",
                    y="drawdown_pct",
                    color="label",
                    title="Drawdown Journey (%)",
                    labels={"drawdown_pct": "Drawdown %", "day": "Date", "label": "Run"},
                )
            )

            figures.append(
                px.box(
                    daily_df,
                    x="label",
                    y="pnl",
                    points="outliers",
                    title="Daily P&L Distribution",
                    labels={"label": "Run", "pnl": "Daily P&L (INR)"},
                )
            )

            monthly = daily_df.groupby(["label", "month"], as_index=False)["pnl"].sum()
            figures.append(
                px.bar(
                    monthly,
                    x="month",
                    y="pnl",
                    color="label",
                    barmode="group",
                    title="Monthly P&L Comparison",
                    labels={"month": "Month", "pnl": "PnL (INR)", "label": "Run"},
                )
            )

        metric_cols = [
            "total_return_pct",
            "win_rate_pct",
            "profit_factor",
            "execution_rate_pct",
            "max_drawdown_pct",
            "avg_trade_pnl",
        ]
        metric_rows = summary_df[["label"] + [c for c in metric_cols if c in summary_df.columns]].copy()
        metric_long = metric_rows.melt(id_vars="label", var_name="metric", value_name="value")
        figures.append(
            px.bar(
                metric_long,
                x="label",
                y="value",
                color="metric",
                barmode="group",
                title="Core Metrics Comparison",
                labels={"label": "Run", "value": "Metric Value", "metric": "Metric"},
            )
        )

        figures.append(
            px.scatter(
                summary_df,
                x="max_drawdown_pct",
                y="total_return_pct",
                color="label",
                size=np.clip(summary_df.get("closed_trades", pd.Series([1] * len(summary_df))), 1, None),
                hover_data=["win_rate_pct", "profit_factor", "execution_rate_pct"],
                title="Risk vs Return Frontier",
                labels={
                    "max_drawdown_pct": "Max Drawdown %",
                    "total_return_pct": "Total Return %",
                    "label": "Run",
                },
            )
        )

        decision_df = self._decision_breakdown_df()
        if not decision_df.empty:
            figures.append(
                px.bar(
                    decision_df,
                    x="label",
                    y="count",
                    color="reason",
                    barmode="stack",
                    title="Entry Decision Breakdown (Top Reasons)",
                    labels={"label": "Run", "count": "Count", "reason": "Decision"},
                )
            )

        risk_df = self._risk_breakdown_df()
        if not risk_df.empty:
            figures.append(
                px.bar(
                    risk_df,
                    x="label",
                    y="count",
                    color="reason",
                    barmode="stack",
                    title="Risk Reason Breakdown (Top Reasons)",
                    labels={"label": "Run", "count": "Count", "reason": "Risk Reason"},
                )
            )

        if not trades_df.empty:
            exits = trades_df.groupby(["label", "exit_reason"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
            )
            figures.append(
                px.bar(
                    exits,
                    x="exit_reason",
                    y="net_pnl",
                    color="label",
                    barmode="group",
                    title="Exit Reason vs Net P&L",
                    labels={"exit_reason": "Exit Reason", "net_pnl": "Net P&L (INR)", "label": "Run"},
                )
            )

            direction_perf = trades_df.groupby(["label", "direction"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                win_rate=("realized_pnl", lambda s: _pct((s > 0).sum(), len(s))),
            )
            figures.append(
                px.bar(
                    direction_perf,
                    x="label",
                    y="net_pnl",
                    color="direction",
                    barmode="group",
                    title="LONG vs SHORT Net P&L",
                    labels={"label": "Run", "net_pnl": "Net P&L (INR)", "direction": "Direction"},
                )
            )

            bucket_perf = trades_df.groupby(["label", "entry_bucket"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
                win_rate=("realized_pnl", lambda s: _pct((s > 0).sum(), len(s))),
            )
            figures.append(
                px.bar(
                    bucket_perf,
                    x="entry_bucket",
                    y="net_pnl",
                    color="label",
                    barmode="group",
                    title="Time-of-Day Net P&L (Trade Entry Buckets)",
                    labels={"entry_bucket": "Entry Bucket", "net_pnl": "Net P&L (INR)", "label": "Run"},
                )
            )

            sector_perf = trades_df.groupby(["label", "sector"], as_index=False).agg(
                trades=("realized_pnl", "size"),
                net_pnl=("realized_pnl", "sum"),
            )
            top_sectors = (
                sector_perf.groupby("sector", as_index=False)["trades"]
                .sum()
                .sort_values("trades", ascending=False)
                .head(15)["sector"]
                .tolist()
            )
            sector_perf = sector_perf[sector_perf["sector"].isin(top_sectors)]
            figures.append(
                px.bar(
                    sector_perf,
                    x="sector",
                    y="net_pnl",
                    color="label",
                    barmode="group",
                    title="Top Sector Net P&L Comparison",
                    labels={"sector": "Sector", "net_pnl": "Net P&L (INR)", "label": "Run"},
                )
            )

        if not signals_df.empty:
            regime_perf = signals_df.groupby(["label", "regime"], as_index=False).agg(
                signals=("signal_id", "size"),
                avg_score=("score", "mean"),
                avg_rvol=("rvol", "mean"),
            )
            figures.append(
                px.bar(
                    regime_perf,
                    x="regime",
                    y="signals",
                    color="label",
                    barmode="group",
                    title="Signals by Regime",
                    labels={"regime": "Regime", "signals": "Signal Count", "label": "Run"},
                )
            )

            if "vix_percentile" in signals_df.columns:
                figures.append(
                    px.box(
                        signals_df,
                        x="label",
                        y="vix_percentile",
                        points=False,
                        title="VIX Percentile Distribution by Run",
                        labels={"label": "Run", "vix_percentile": "VIX Percentile"},
                    )
                )

            if "score" in signals_df.columns:
                figures.append(
                    px.histogram(
                        signals_df,
                        x="score",
                        color="label",
                        barmode="overlay",
                        nbins=30,
                        title="Signal Score Distribution",
                        labels={"score": "Signal Score", "label": "Run"},
                    )
                )

        param_df = self._param_sensitivity_df(summary_df)
        if not param_df.empty:
            figures.append(
                px.scatter(
                    param_df,
                    x="value",
                    y="total_return_pct",
                    color="parameter",
                    symbol="label",
                    hover_data=["label", "win_rate_pct", "max_drawdown_pct"],
                    title="Parameter Sensitivity: Value vs Return%",
                    labels={"value": "Parameter Value", "total_return_pct": "Total Return %", "parameter": "Parameter"},
                )
            )

            top_var_params = (
                param_df.groupby("parameter", as_index=False)["value"].nunique()
                .sort_values("value", ascending=False)
                .head(8)["parameter"]
                .tolist()
            )
            sub = param_df[param_df["parameter"].isin(top_var_params)]
            figures.append(
                px.scatter(
                    sub,
                    x="value",
                    y="total_return_pct",
                    color="label",
                    facet_col="parameter",
                    facet_col_wrap=4,
                    title="Top Varying Parameters (Optimization Candidates)",
                    labels={"value": "Param Value", "total_return_pct": "Return %", "label": "Run"},
                )
            )

        blocks: List[str] = []
        include_js = True
        for fig in figures:
            fig.update_layout(template="plotly_white", legend_title_text="")
            blocks.append(self._fig_to_html(fig, include_js=include_js))
            include_js = False

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_list_html = "".join(f"<li>{b.label}: {b.history_path}</li>" for b in self.bundles)

        html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
    .card {{ background: #ffffff; border-radius: 12px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 6px rgba(0,0,0,0.08); }}
    h1, h2 {{ margin: 0 0 10px 0; }}
    ul {{ margin-top: 8px; }}
    .muted {{ color: #475569; font-size: 0.95rem; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>{title}</h1>
    <p class=\"muted\">Generated at: {generated_at}</p>
    <p class=\"muted\">Runs included: {len(self.bundles)}</p>
    <ul>{file_list_html}</ul>
  </div>
  {''.join(f'<div class="card">{b}</div>' for b in blocks)}
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    out: List[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out


def _discover_from_sources(sources: Sequence[Dict[str, Any]]) -> Tuple[List[Path], List[str]]:
    """
    Resolve default source entries of shape: {"path": Path, "label": str}.

    Behavior per source:
    - If `path` points to a JSON file, use that exact file.
    - If `path` points to a directory, pick latest backtest_history_*.json.
    - `dir` is still accepted as a legacy fallback key.
    """
    files: List[Path] = []
    labels: List[str] = []

    for src in sources:
        raw_path = src.get("path", src.get("dir", ""))
        source_path = Path(raw_path)
        label = str(src.get("label", source_path.name))

        if not source_path.exists():
            continue

        if source_path.is_file():
            if source_path.name.startswith("backtest_history_") and source_path.suffix.lower() == ".json":
                files.append(source_path.resolve())
                labels.append(label)
            continue

        candidates = sorted(source_path.glob("backtest_history_*.json"))
        if candidates:
            latest = candidates[-1].resolve()
            files.append(latest)
            labels.append(label)

    return _dedupe_paths(files), labels


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Graph-based analyzer for one or many V6 history JSON files")
    parser.add_argument("history_files", nargs="*", help="Explicit history JSON files")
    parser.add_argument("--labels", nargs="*", help="Custom labels in same order as history_files")
    parser.add_argument(
        "--output",
        default="",
        help="Output HTML path (default: backtest_v6/analysis/advanced_graph_analysis_<timestamp>.html)",
    )
    parser.add_argument("--title", default="V6 Backtest Graph Analysis", help="Dashboard title")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    explicit_files = [Path(p) for p in args.history_files]

    if explicit_files:
        all_files = _dedupe_paths(explicit_files)
        default_labels: Optional[List[str]] = None
    else:
        all_files, auto_labels = _discover_from_sources(DEFAULT_HISTORY_SOURCES)
        default_labels = auto_labels

    if not all_files:
        print("No history files found. Provide file paths or ensure history folders have backtest_history_*.json")
        return 1

    if args.labels and len(args.labels) != len(explicit_files):
        print("Error: --labels count must match the number of explicit history_files")
        return 1

    labels: Optional[List[str]] = None
    if explicit_files and args.labels:
        label_map = {p.resolve(): lbl for p, lbl in zip(explicit_files, args.labels)}
        labels = [label_map.get(fp.resolve(), _safe_label_from_path(fp)) for fp in all_files]
    elif not explicit_files:
        labels = default_labels

    stamp = datetime.now().strftime("%d-%m-%Y_%I-%M_%p").lower()
    output = Path(args.output) if args.output else (ROOT / "analysis" / f"advanced_graph_analysis_{stamp}.html")

    analyzer = GraphAnalyzer(all_files, labels=labels)
    analyzer.load()
    out = analyzer.build_html(output_path=output, title=args.title)

    print(f"Graph dashboard exported: {out}")
    print(f"Runs analyzed: {len(analyzer.bundles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
