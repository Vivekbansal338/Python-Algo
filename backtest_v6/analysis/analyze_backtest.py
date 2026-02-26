"""
V6 Advanced Backtest Analyzer

Advanced diagnostics for `backtest_v6` history output.
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
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "p10": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "max": 0.0,
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


class AdvancedBacktestAnalyzer:
    def __init__(self, json_path: str, use_market_data: bool = True):
        self.json_path = Path(json_path)
        if not self.json_path.exists():
            raise FileNotFoundError(f"History file not found: {json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        self.run = self.data.get("run", {})
        self.summary = self.data.get("summary", {})
        self.daily_results = self.data.get("daily_results", [])
        self.trade_records = self.data.get("trade_records", [])
        self.signal_records = self.data.get("signal_records", [])
        self.position_records = self.data.get("position_records", [])
        self.all_position_records = self.data.get("all_position_records", [])

        self.market = MarketDataProvider(self.run.get("data_root")) if use_market_data else None
        self.daily_df = pd.DataFrame(self.daily_results)
        self.trade_df = self._build_trade_df()
        self.touch_df: Optional[pd.DataFrame] = None

    def _build_trade_df(self) -> pd.DataFrame:
        tdf = pd.DataFrame(self.trade_records)
        if tdf.empty:
            return tdf

        for col, val in {
            "trade_id": "",
            "symbol": "",
            "sector": "UNKNOWN",
            "direction": "",
            "entry_time": None,
            "exit_time": None,
            "entry_price": 0.0,
            "initial_qty": 0,
            "realized_pnl": 0.0,
            "exit_reason": "",
        }.items():
            if col not in tdf.columns:
                tdf[col] = val

        tdf["entry_time"] = pd.to_datetime(tdf["entry_time"], errors="coerce")
        tdf["exit_time"] = pd.to_datetime(tdf["exit_time"], errors="coerce")
        tdf["entry_price"] = pd.to_numeric(tdf["entry_price"], errors="coerce").fillna(0.0)
        tdf["initial_qty"] = pd.to_numeric(tdf["initial_qty"], errors="coerce").fillna(0).astype(int)
        tdf["realized_pnl"] = pd.to_numeric(tdf["realized_pnl"], errors="coerce").fillna(0.0)
        tdf["entry_notional"] = tdf["entry_price"] * tdf["initial_qty"]
        tdf["entry_day"] = tdf["entry_time"].dt.date

        sdf = pd.DataFrame(self.signal_records)
        if not sdf.empty and "executed_trade_id" in sdf.columns:
            sdf = sdf.copy()
            sdf["trade_id"] = sdf["executed_trade_id"].astype(str)
            sdf["timestamp"] = pd.to_datetime(sdf.get("timestamp"), errors="coerce")
            sdf = sdf.drop_duplicates(subset=["trade_id"], keep="last")
            rename = {c: f"sig_{c}" for c in sdf.columns if c != "trade_id"}
            sdf = sdf.rename(columns=rename)
            tdf = tdf.merge(sdf, on="trade_id", how="left")

        pdf = pd.DataFrame(self.position_records)
        if not pdf.empty and "executed_trade_id" in pdf.columns:
            pdf = pdf.copy()
            pdf["trade_id"] = pdf["executed_trade_id"].astype(str)
            pdf["timestamp"] = pd.to_datetime(pdf.get("timestamp"), errors="coerce")
            pdf = pdf.drop_duplicates(subset=["trade_id"], keep="last")
            rename = {c: f"pos_{c}" for c in pdf.columns if c != "trade_id"}
            pdf = pdf.rename(columns=rename)
            tdf = tdf.merge(pdf, on="trade_id", how="left")

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
        return tdf

    def _core_trade_stats(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"total_trades": 0}
        pnls = self.trade_df["realized_pnl"]
        pos = pnls[pnls > 0]
        neg = pnls[pnls < 0]
        total = int(pnls.shape[0])
        wins = int(pos.shape[0])
        losses = int(neg.shape[0])
        pf = (float(pos.sum()) / abs(float(neg.sum()))) if neg.shape[0] else float("inf")
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": int((pnls == 0).sum()),
            "win_rate_pct": round(_pct(wins, total), 2),
            "net_pnl": round(float(pnls.sum()), 2),
            "sum_positive_pnl": round(float(pos.sum()), 2) if not pos.empty else 0.0,
            "sum_negative_pnl": round(float(neg.sum()), 2) if not neg.empty else 0.0,
            "avg_trade_pnl": round(float(pnls.mean()), 2),
            "best_trade": round(float(pnls.max()), 2),
            "worst_trade": round(float(pnls.min()), 2),
            "profit_factor": round(pf, 2) if np.isfinite(pf) else "Inf",
        }

    def _core_equity(self) -> Dict[str, Any]:
        ini = _to_float(self.summary.get("initial_equity", 0.0))
        fin = _to_float(self.summary.get("final_equity", ini))
        ret = _to_float(self.summary.get("total_return", fin - ini))
        ret_pct = _to_float(self.summary.get("total_return_pct", _pct(fin - ini, ini)))

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
            "max_drawdown_inr": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
        }

    def _execution(self) -> Dict[str, Any]:
        all_signals = len(self.data.get("all_signal_records", []))
        executed = len(self.signal_records)
        return {
            "all_a_grade_signals": all_signals,
            "executed_signals": executed,
            "execution_rate_pct": round(_pct(executed, all_signals), 2),
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

    def _blockers(self) -> Dict[str, Any]:
        raw_dec = self.summary.get("decision_counts") or Counter(
            x.get("entry_decision", "NA") for x in self.all_position_records if x.get("entry_decision")
        )
        raw_risk = self.summary.get("risk_reason_counts") or Counter(
            x.get("risk_reason", "NA") for x in self.all_position_records if x.get("risk_reason")
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
        for i, s, g in itertools.product(
            ["UP", "DOWN"], ["UP", "DOWN"], ["UP", "DOWN"]
        ):
            sub = valid[
                (valid["index_dir"] == i)
                & (valid["sector_dir"] == s)
                & (valid["signal_dir"] == g)
            ]
            trades = int(sub.shape[0])
            wins = int((sub["realized_pnl"] > 0).sum())
            pos_pnl = sub.loc[sub["realized_pnl"] > 0, "realized_pnl"]
            neg_pnl = sub.loc[sub["realized_pnl"] < 0, "realized_pnl"]
            rows.append(
                {
                    "index_dir": i,
                    "sector_dir": s,
                    "signal_dir": g,
                    "trades": trades,
                    "win_rate_pct": round(_pct(wins, trades), 2),
                    "sum_positive_pnl": round(float(pos_pnl.sum()), 2) if not pos_pnl.empty else 0.0,
                    "sum_negative_pnl": round(float(neg_pnl.sum()), 2) if not neg_pnl.empty else 0.0,
                    "net_pnl": round(float(sub["realized_pnl"].sum()) if trades else 0.0, 2),
                }
            )
        aligned = valid[
            (valid["index_dir"] == valid["sector_dir"])
            & (valid["sector_dir"] == valid["signal_dir"])
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
            by_dir.append(
                {
                    "direction": str(d),
                    "trades": int(g.shape[0]),
                    "avg_stop_pct": round(float(g["stop_pct"].mean()), 4),
                    "avg_target_pct": round(float(g["target_pct"].mean()), 4),
                    "avg_t_s_ratio": round(float(g["t_s_ratio"].mean()), 4),
                    "avg_realized_r": round(float(g["realized_r"].mean()), 4),
                    "win_rate_pct": round(_pct(int((g["realized_pnl"] > 0).sum()), int(g.shape[0])), 2),
                }
            )

        return {
            "available": True,
            "summary_stop_pct": _numeric_summary(df["stop_pct"]),
            "summary_target_pct": _numeric_summary(df["target_pct"]),
            "summary_t_s_ratio": _numeric_summary(df["t_s_ratio"]),
            "summary_realized_r": _numeric_summary(df["realized_r"]),
            "by_direction": by_dir,
        }

    def target_stop_touch_analysis(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"available": False, "reason": "No trades"}
        if not self.market or not self.market.available:
            msg = "Market data not available"
            if self.market and self.market.last_error:
                msg = f"{msg}: {self.market.last_error}"
            return {"available": False, "reason": msg}
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
                if t_ts < s_ts:
                    first = "TARGET_FIRST"
                elif s_ts < t_ts:
                    first = "STOP_FIRST"
                else:
                    first = "SAME_BAR_BOTH"
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
            perf.append(
                {
                    "first_touch": str(cat),
                    "trades": trades,
                    "win_rate_pct": round(_pct(wins, trades), 2),
                    "pnl": round(float(g["pnl"].sum()), 2),
                }
            )

        return {
            "available": True,
            "total_trades_checked": total,
            "first_touch_breakdown": {
                k: {"count": int(v), "pct": round(_pct(v, total), 2)} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
            },
            "first_touch_performance": sorted(perf, key=lambda x: x["trades"], reverse=True),
        }

    def capital_utilization(self) -> Dict[str, Any]:
        if self.trade_df.empty:
            return {"summary": {}}

        daily_start = {}
        daily_pnl = {}
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
            total_entry = float(g["entry_notional"].sum())
            rows.append(
                {
                    "day": str(day),
                    "trades": int(g.shape[0]),
                    "start_equity": round(start_eq, 2) if not pd.isna(start_eq) else None,
                    "day_pnl": round(daily_pnl.get(day, float(g["realized_pnl"].sum())), 2),
                    "total_entry_notional": round(total_entry, 2),
                    "peak_deployed_notional": round(peak, 2),
                    "peak_utilization_pct": round(_pct(peak, start_eq), 2) if (not pd.isna(start_eq) and start_eq > 0) else None,
                }
            )

        if not rows:
            return {"summary": {}}

        rdf = pd.DataFrame(rows)
        summary = {
            "days_with_trades": int(rdf.shape[0]),
            "avg_peak_deployed_notional": round(float(rdf["peak_deployed_notional"].mean()), 2),
            "max_peak_deployed_notional": round(float(rdf["peak_deployed_notional"].max()), 2),
            "avg_peak_utilization_pct": round(float(pd.to_numeric(rdf["peak_utilization_pct"], errors="coerce").mean()), 2),
        }
        return {"summary": summary}

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
            g = g.sort_values(by=["entry_time", "trade_id"])  # first trade in day
            first = g.iloc[0]
            fpnl = float(first["realized_pnl"])
            label = "FIRST_WIN" if fpnl > 0 else "FIRST_LOSS" if fpnl < 0 else "FIRST_BREAKEVEN"
            day_pnl = day_pnl_map.get(day, float(g["realized_pnl"].sum()))
            rows.append(
                {
                    "day": str(day),
                    "first_trade_outcome": label,
                    "first_trade_pnl": round(fpnl, 2),
                    "day_pnl": round(day_pnl, 2),
                    "day_profit": bool(day_pnl > 0),
                }
            )

        if not rows:
            return {"rows": [], "correlation": None}

        rdf = pd.DataFrame(rows)
        summary_rows = []
        for label, g in rdf.groupby("first_trade_outcome"):
            # Get all days matching this first_trade_outcome
            matching_days = set(pd.to_datetime(g["day"], errors="coerce").dt.date)
            # Filter trade_df to only trades on these days
            trades_on_matching_days = self.trade_df[self.trade_df["entry_day"].isin(matching_days)]
            
            # Calculate trade metrics for trades on these days
            pnls = trades_on_matching_days["realized_pnl"]
            pos_pnl = pnls[pnls > 0]
            neg_pnl = pnls[pnls < 0]
            total_trades = int(pnls.shape[0])
            wins = int((pnls > 0).sum())
            
            summary_rows.append(
                {
                    "first_trade_outcome": str(label),
                    "days": int(g.shape[0]),
                    "day_profit_rate_pct": round(_pct(int(g["day_profit"].sum()), int(g.shape[0])), 2),
                    "avg_day_pnl": round(float(g["day_pnl"].mean()), 2),
                    "median_day_pnl": round(float(g["day_pnl"].median()), 2),
                    "win_rate_pct": round(_pct(wins, total_trades), 2),
                    "sum_positive_pnl": round(float(pos_pnl.sum()), 2) if not pos_pnl.empty else 0.0,
                    "sum_negative_pnl": round(float(neg_pnl.sum()), 2) if not neg_pnl.empty else 0.0,
                    "net_pnl": round(float(pnls.sum()), 2),
                }
            )

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
            rows.append(
                {
                    "regime": str(regime),
                    "trades": trades,
                    "win_rate_pct": round(_pct(wins, trades), 2),
                    "pnl": round(float(g["realized_pnl"].sum()), 2),
                }
            )
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
            rows.append(
                {
                    "bucket": str(b),
                    "trades": trades,
                    "win_rate_pct": round(_pct(wins, trades), 2),
                    "pnl": round(float(g["realized_pnl"].sum()), 2),
                }
            )
        return {"rows": sorted(rows, key=lambda x: x["trades"], reverse=True)}

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
            },
            "trade_statistics": self._core_trade_stats(),
            "equity_analysis": self._core_equity(),
            "execution_metrics": self._execution(),
            "daily_performance": self._daily(),
            "direction_matrix_index_sector_signal": self.direction_matrix(),
            "risk_target_analysis": self.risk_target_analysis(),
            "target_stop_touch_analysis": self.target_stop_touch_analysis(),
            "capital_utilization": self.capital_utilization(),
            "first_trade_effect": self.first_trade_effect(),
            "regime_performance": self.regime_performance(),
            "time_bucket_performance": self.time_bucket_performance(),
        }

    @staticmethod
    def _print_table(title: str, rows: List[Dict[str, Any]], cols: List[Tuple[str, str]], max_rows: Optional[int] = None):
        print(f"\n{title}")
        if not rows:
            print("  (no data)")
            return
        use = rows[: max_rows or len(rows)]

        def fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.2f}"
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
        print("V6 ADVANCED BACKTEST ANALYSIS")
        print(line)

        m = out["metadata"]
        print(f"Run: {m.get('run_id')} | {m.get('run_status')} | {m.get('start_date')} -> {m.get('end_date')}")
        print(f"History: {m.get('history_file')}")
        print(f"Market data available: {m.get('market_data_available')}")

        print("\nCore:")
        print("  Trade Stats:", out["trade_statistics"])
        print("  Equity:", out["equity_analysis"])
        print("  Execution:", out["execution_metrics"])
        print("  Daily:", out["daily_performance"])

        self._print_table(
            "Index-Sector-Signal Matrix",
            out["direction_matrix_index_sector_signal"].get("rows", []),
            [("index_dir", "Index"), ("sector_dir", "Sector"), ("signal_dir", "Signal"), ("trades", "Trades"), ("win_rate_pct", "WinRate%"), ("net_pnl", "NetPnL")],
        )

        print("\nRisk/Target Summary:")
        print(out["risk_target_analysis"])

        touch = out["target_stop_touch_analysis"]
        print("\nTarget/Stop Touch:")
        if touch.get("available"):
            print(f"  Total checked: {touch.get('total_trades_checked')}")
            self._print_table(
                "First Touch Breakdown",
                [{"first_touch": k, "count": v.get("count"), "pct": v.get("pct")} for k, v in touch.get("first_touch_breakdown", {}).items()],
                [("first_touch", "FirstTouch"), ("count", "Count"), ("pct", "Pct")],
            )
            self._print_table(
                "First Touch Performance",
                touch.get("first_touch_performance", []),
                [("first_touch", "FirstTouch"), ("trades", "Trades"), ("win_rate_pct", "WinRate%"), ("pnl", "PnL")],
            )
        else:
            print(f"  {touch.get('reason')}")

        print("\nCapital Utilization Summary:")
        print(out["capital_utilization"].get("summary", {}))

        first = out["first_trade_effect"]
        print(f"\nFirst trade correlation with day pnl: {first.get('correlation')}")
        self._print_table(
            "First Trade Outcome Effect",
            first.get("rows", []),
            [("first_trade_outcome", "FirstOutcome"), ("days", "Days"), ("day_profit_rate_pct", "DayProfit%"), ("avg_day_pnl", "AvgDayPnL"), ("win_rate_pct", "WinRate%"), ("net_pnl", "NetPnL")],
        )

        self._print_table(
            "Regime Performance",
            out["regime_performance"].get("rows", []),
            [("regime", "Regime"), ("trades", "Trades"), ("win_rate_pct", "WinRate%"), ("pnl", "PnL")],
            max_rows=top,
        )

        self._print_table(
            "Time Bucket Performance",
            out["time_bucket_performance"].get("rows", []),
            [("bucket", "Bucket"), ("trades", "Trades"), ("win_rate_pct", "WinRate%"), ("pnl", "PnL")],
            max_rows=top,
        )

        print("\n" + line + "\n")
        return out

    @staticmethod
    def export_json(analysis: Dict[str, Any], output_path: str) -> str:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        return output_path


def _find_latest_history_file() -> Optional[Path]:
    history_dir = Path(__file__).parent.parent / "history"
    if not history_dir.exists():
        return None
    files = sorted(history_dir.glob("backtest_history_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advanced V6 backtest analysis")
    parser.add_argument("history_file", nargs="?", help="History JSON file")
    parser.add_argument("--latest", action="store_true", help="Use latest history file")
    parser.add_argument("--export", action="store_true", help="Export analysis JSON to analysis folder")
    parser.add_argument("--no-market-data", action="store_true", help="Disable market-data dependent analysis")
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
        print("Error: no history file found. Use --latest or provide a file path.", file=sys.stderr)
        return 1

    try:
        analyzer = AdvancedBacktestAnalyzer(str(history_file), use_market_data=not args.no_market_data)
        analysis = analyzer.print_report(top=max(1, int(args.top)))

        if args.export:
            analysis_dir = Path(__file__).resolve().parent
            dt_match = re.search(
                r"backtest_history_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}_(?:am|pm))",
                history_file.name,
                re.IGNORECASE,
            )
            if dt_match:
                export_name = f"advanced_analysis_{dt_match.group(1)}.json"
            else:
                stamp = datetime.now()
                date_part = stamp.strftime("%d-%m-%Y")
                time_part = stamp.strftime("%I-%M_%p").lower()
                export_name = f"advanced_analysis_{date_part}_{time_part}.json"
            export_path = analysis_dir / export_name
            out = AdvancedBacktestAnalyzer.export_json(analysis, str(export_path))
            print(f"Advanced analysis exported to: {out}")

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
