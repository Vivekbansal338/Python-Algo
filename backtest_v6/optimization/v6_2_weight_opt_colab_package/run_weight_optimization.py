"""
V6.2 weight optimization pipeline (Colab-ready).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time as _time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import optuna
import pandas as pd

from engine.sector_engine_v6_2_opt import SectorBacktesterV6

try:
    from engine.gpu_precompute import precompute_all, HAS_CUPY
except ImportError:
    precompute_all = None  # type: ignore[assignment]
    HAS_CUPY = False

try:
    from scipy.stats import qmc
except Exception:
    qmc = None


PARAM_KEYS = ["structural", "shortterm", "intraday", "breadth", "nifty", "threshold"]
WEIGHT_KEYS = ["structural", "shortterm", "intraday", "breadth", "nifty"]

BOUNDS = {
    "structural": (0.0, 150.0),
    "shortterm": (0.0, 150.0),
    "intraday": (0.0, 200.0),
    "breadth": (0.0, 150.0),
    "nifty": (0.0, 250.0),
    "threshold": (0.0, 35.0),
}

GRID = {
    "structural": (0, 5, 10, 20, 40, 80, 120, 160),
    "shortterm": (0, 5, 10, 20, 40, 80, 120, 160),
    "intraday": (0, 5, 10, 20, 40, 80, 120, 160),
    "breadth": (0, 5, 10, 20, 40, 80, 120, 160),
    "nifty": (0, 10, 30, 60, 120, 180, 240),
    "threshold": (0, 5, 10, 15, 20, 25, 30, 35),
}

def _fmt_duration(secs: float) -> str:
    """Format seconds into human-readable HH:MM:SS or MM:SS."""
    secs = max(0.0, secs)
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{secs:.1f}s"


def _progress_line(label: str, i: int, total: int, t0: float, best_obj: Optional[float] = None) -> str:
    """Build a progress line with elapsed, ETA, speed, and best score."""
    elapsed = _time.time() - t0
    speed = i / elapsed if elapsed > 0 else 0.0
    remaining = (total - i) / speed if speed > 0 else 0.0
    parts = [
        f"[{label}] {i}/{total}",
        f"elapsed {_fmt_duration(elapsed)}",
        f"ETA {_fmt_duration(remaining)}",
        f"{speed:.1f} trial/s" if speed >= 0.1 else f"{1/speed:.1f} s/trial" if speed > 0 else "",
    ]
    if best_obj is not None:
        parts.append(f"best={best_obj:.4f}")
    return "  |  ".join(p for p in parts if p)


DEFAULT_HURDLES = {
    "return_pct": 15.32,
    "max_drawdown_pct": 9.12,
    "profit_factor": 1.09,
    "win_rate_pct": 63.44,
    "expectancy": 64.43,
}


@dataclass(frozen=True)
class Config:
    structural: float
    shortterm: float
    intraday: float
    breadth: float
    nifty: float
    threshold: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "structural": float(self.structural),
            "shortterm": float(self.shortterm),
            "intraday": float(self.intraday),
            "breadth": float(self.breadth),
            "nifty": float(self.nifty),
            "threshold": float(self.threshold),
        }

    def as_weights(self) -> Dict[str, float]:
        d = self.as_dict()
        return {k: d[k] for k in WEIGHT_KEYS}

    def key(self, nd: int = 4) -> Tuple[float, ...]:
        d = self.as_dict()
        return tuple(round(float(d[k]), nd) for k in PARAM_KEYS)

    def sparsity(self, eps: float = 5.0) -> int:
        return sum(1 for k in WEIGHT_KEYS if abs(float(getattr(self, k))) <= eps)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Config":
        return Config(
            structural=float(d["structural"]),
            shortterm=float(d["shortterm"]),
            intraday=float(d["intraday"]),
            breadth=float(d["breadth"]),
            nifty=float(d["nifty"]),
            threshold=float(d["threshold"]),
        )


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass(frozen=True)
class Metrics:
    net_pnl: float
    return_pct: float
    drawdown_pct: float
    profit_factor: float
    expectancy: float
    win_rate_pct: float
    sortino: float
    trades: int
    pos_pnl: float
    neg_pnl: float
    bucket_conc: float
    regime_conc: float
    conc_share: float
    status: str


@dataclass
class Eval:
    cfg: Config
    phase: str
    train: Metrics
    test: Metrics
    fold_train: List[Metrics]
    fold_test: List[Metrics]
    obj: float
    trade_pen: float
    stab_pen: float
    conc_pen: float
    total_pen: float
    overfit_gap: float

    def row(self) -> Dict[str, Any]:
        d = self.cfg.as_dict()
        return {
            "phase": self.phase,
            "w_structural": d["structural"],
            "w_shortterm": d["shortterm"],
            "w_intraday": d["intraday"],
            "w_breadth": d["breadth"],
            "w_nifty": d["nifty"],
            "bias_threshold": d["threshold"],
            "sparsity_near_zero": self.cfg.sparsity(),
            "objective_score": self.obj,
            "overfit_gap": self.overfit_gap,
            "trade_penalty": self.trade_pen,
            "instability_penalty": self.stab_pen,
            "concentration_penalty": self.conc_pen,
            "total_penalty": self.total_pen,
            "train_return_pct": self.train.return_pct,
            "train_drawdown_pct": self.train.drawdown_pct,
            "train_pf": self.train.profit_factor,
            "train_expectancy": self.train.expectancy,
            "train_win_rate_pct": self.train.win_rate_pct,
            "train_sortino": self.train.sortino,
            "train_trades": self.train.trades,
            "oos_return_pct": self.test.return_pct,
            "oos_drawdown_pct": self.test.drawdown_pct,
            "oos_pf": self.test.profit_factor,
            "oos_expectancy": self.test.expectancy,
            "oos_win_rate_pct": self.test.win_rate_pct,
            "oos_sortino": self.test.sortino,
            "oos_trades": self.test.trades,
            "oos_concentration": self.test.conc_share,
            "oos_bucket_concentration": self.test.bucket_conc,
            "oos_regime_concentration": self.test.regime_conc,
        }


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def pf(pos: float, neg: float) -> float:
    if neg < 0:
        return pos / abs(neg)
    if pos > 0:
        return 10.0
    return 0.0


def score_base(m: Metrics) -> float:
    return (
        0.30 * sigmoid(m.return_pct / 8.0)
        + 0.20 * sigmoid(m.sortino / 1.8)
        + 0.15 * clamp(min(m.profit_factor, 3.0) / 3.0, 0.0, 1.0)
        + 0.15 * sigmoid(m.expectancy / 120.0)
        + 0.05 * clamp((m.win_rate_pct - 45.0) / 30.0, 0.0, 1.0)
        - 0.15 * clamp(m.drawdown_pct / 20.0, 0.0, 1.0)
    )


def add_months(d: date, months: int) -> date:
    y = d.year + ((d.month - 1 + months) // 12)
    m = ((d.month - 1 + months) % 12) + 1
    return date(y, m, 1)


def build_folds(start: date, end: date, train_m: int, test_m: int) -> List[Fold]:
    out: List[Fold] = []
    anchor = date(start.year, start.month, 1)
    fid = 1
    while True:
        tr_s = max(start, anchor)
        tr_e = min(end, add_months(anchor, train_m) - timedelta(days=1))
        te_s = add_months(anchor, train_m)
        te_e = min(end, add_months(anchor, train_m + test_m) - timedelta(days=1))
        if te_s > end:
            break
        if tr_s <= tr_e and te_s <= te_e:
            out.append(Fold(fid, tr_s, tr_e, te_s, te_e))
            fid += 1
        anchor = add_months(anchor, 1)
        if anchor > end:
            break
    return out


def time_bucket(t: dt_time) -> str:
    if t < dt_time(10, 30):
        return "OPEN_0925_1030"
    if t < dt_time(12, 0):
        return "MID_1030_1200"
    if t < dt_time(13, 15):
        return "LUNCH_1200_1315"
    if t <= dt_time(14, 5):
        return "AFTERNOON_1315_1405"
    return "POST_1405"


def drawdown_pct(curve: Sequence[float]) -> float:
    if not curve:
        return 0.0
    peak = float(curve[0])
    max_dd = 0.0
    for eq in curve:
        eq = float(eq)
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return max_dd


def aggregate(ms: Sequence[Metrics]) -> Metrics:
    if not ms:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "NO_DATA")
    trades = int(sum(m.trades for m in ms))
    pos = float(sum(m.pos_pnl for m in ms))
    neg = float(sum(m.neg_pnl for m in ms))
    expectancy = float(sum(m.expectancy * m.trades for m in ms) / trades) if trades else 0.0
    wr = float(sum((m.win_rate_pct / 100.0) * m.trades for m in ms) / trades * 100.0) if trades else 0.0
    statuses = {m.status for m in ms}
    return Metrics(
        net_pnl=float(sum(m.net_pnl for m in ms)),
        return_pct=float(np.mean([m.return_pct for m in ms])),
        drawdown_pct=float(max(m.drawdown_pct for m in ms)),
        profit_factor=float(pf(pos, neg)),
        expectancy=expectancy,
        win_rate_pct=wr,
        sortino=float(np.mean([m.sortino for m in ms])),
        trades=trades,
        pos_pnl=pos,
        neg_pnl=neg,
        bucket_conc=float(max(m.bucket_conc for m in ms)),
        regime_conc=float(max(m.regime_conc for m in ms)),
        conc_share=float(max(m.conc_share for m in ms)),
        status="COMPLETED" if statuses == {"COMPLETED"} else ",".join(sorted(statuses)),
    )


def metrics_from_engine(engine: SectorBacktesterV6) -> Metrics:
    if getattr(engine, "run_status", "") != "COMPLETED":
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, str(getattr(engine, "run_status", "UNKNOWN")))

    pnls = [float(t.realized_pnl) for t in engine.trade_history]
    pos = float(sum(p for p in pnls if p > 0))
    neg = float(sum(p for p in pnls if p < 0))
    trades = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    expectancy = float(np.mean(pnls)) if pnls else 0.0
    wr = wins / trades * 100.0 if trades else 0.0

    ini = float(engine.initial_equity)
    fin = float(ini + engine.realized_pnl)
    ret = ((fin / ini) - 1.0) * 100.0 if ini > 0 else 0.0
    curve = [ini]
    for t in sorted(engine.trade_history, key=lambda x: x.exit_time or x.entry_time):
        curve.append(curve[-1] + float(t.realized_pnl))
    dd = drawdown_pct(curve)

    daily_returns = []
    for r in engine.day_results:
        s = float(r.start_equity)
        if s > 0:
            daily_returns.append(float(r.pnl) / s)
    if daily_returns:
        mean_r = float(np.mean(daily_returns))
        downside = math.sqrt(float(np.mean([min(0.0, x) ** 2 for x in daily_returns])))
        sortino = (mean_r / downside * math.sqrt(252.0)) if downside > 0 else (10.0 if mean_r > 0 else 0.0)
    else:
        sortino = 0.0

    exec_rows = [r for r in engine.signal_records if bool(r.get("executed_trade"))]
    if exec_rows:
        b = Counter()
        g = Counter()
        for row in exec_rows:
            ts = pd.to_datetime(row.get("timestamp"), errors="coerce")
            if not pd.isna(ts):
                b[time_bucket(ts.time())] += 1
            g[str(row.get("regime", "UNKNOWN"))] += 1
        n = len(exec_rows)
        b_share = max(b.values()) / n if b else 0.0
        g_share = max(g.values()) / n if g else 0.0
    elif trades > 0:
        b = Counter(time_bucket(pd.Timestamp(t.entry_time).time()) for t in engine.trade_history)
        b_share = max(b.values()) / trades if b else 0.0
        g_share = 0.0
    else:
        b_share = 0.0
        g_share = 0.0

    return Metrics(
        net_pnl=float(fin - ini),
        return_pct=float(ret),
        drawdown_pct=float(dd),
        profit_factor=float(pf(pos, neg)),
        expectancy=float(expectancy),
        win_rate_pct=float(wr),
        sortino=float(sortino),
        trades=int(trades),
        pos_pnl=pos,
        neg_pnl=neg,
        bucket_conc=float(b_share),
        regime_conc=float(g_share),
        conc_share=float(max(b_share, g_share)),
        status="COMPLETED",
    )


class Optimizer:
    def __init__(
        self,
        data_root: Path,
        folds: Sequence[Fold],
        min_trades: int,
        conc_limit: float,
        spread_bps: float,
        circuit_pct: float,
        precompute: bool = True,
        global_start: Optional[date] = None,
        global_end: Optional[date] = None,
    ):
        self.folds = list(folds)
        self.min_trades = int(min_trades)
        self.conc_limit = float(conc_limit)
        self.engine = SectorBacktesterV6(
            data_root=data_root,
            synthetic_spread_bps=spread_bps,
            synthetic_circuit_pct=circuit_pct,
            record_history=False,
            verbose=False,
        )
        if not self.engine.initialize():
            raise RuntimeError("Engine initialization failed.")
        self.cache: Dict[Tuple[Any, ...], Metrics] = {}

        # ── GPU / CPU indicator pre-computation ──
        if precompute and precompute_all is not None:
            gs = global_start or min(f.train_start for f in self.folds)
            ge = global_end or max(f.test_end for f in self.folds)
            precompute_all(self.engine, gs, ge, verbose=True)
        elif precompute:
            print("[warn] gpu_precompute module not available — running without pre-computation")

    def _key(self, cfg: Optional[Config], s: date, e: date, default_mode: bool) -> Tuple[Any, ...]:
        prefix = ("DEFAULT_BEHAVIOR",) if default_mode else cfg.key()
        return prefix + (s.isoformat(), e.isoformat())

    def run_range(self, cfg: Optional[Config], s: date, e: date, default_mode: bool = False) -> Metrics:
        k = self._key(cfg, s, e, default_mode)
        if k in self.cache:
            return self.cache[k]
        if default_mode:
            self.engine.set_sector_params(None, None)
        else:
            self.engine.set_sector_params(cfg.as_weights(), cfg.threshold)
        self.engine.run_backtest(s, e)
        m = metrics_from_engine(self.engine)
        self.cache[k] = m
        return m

    def evaluate(self, cfg: Config, phase: str) -> Eval:
        tr = []
        te = []
        for f in self.folds:
            tr.append(self.run_range(cfg, f.train_start, f.train_end, default_mode=False))
            te.append(self.run_range(cfg, f.test_start, f.test_end, default_mode=False))
        tr_agg = aggregate(tr)
        te_agg = aggregate(te)
        tr_scores = [score_base(x) for x in tr]
        te_scores = [score_base(x) for x in te]
        trade_pen = clamp((self.min_trades - te_agg.trades) / self.min_trades * 0.35, 0.0, 0.35) if te_agg.trades < self.min_trades else 0.0
        stab_pen = clamp(float(np.std(te_scores)) / 0.20 * 0.20, 0.0, 0.20) if len(te_scores) > 1 else 0.0
        conc_pen = clamp((te_agg.conc_share - self.conc_limit) / max(1e-9, 1 - self.conc_limit) * 0.20, 0.0, 0.20) if te_agg.conc_share > self.conc_limit else 0.0
        total_pen = trade_pen + stab_pen + conc_pen
        obj = score_base(te_agg) - total_pen
        overfit = float(np.mean(tr_scores) - np.mean(te_scores)) if tr_scores and te_scores else 0.0
        return Eval(cfg, phase, tr_agg, te_agg, tr, te, obj, trade_pen, stab_pen, conc_pen, total_pen, overfit)

    def evaluate_default(self) -> Tuple[List[Metrics], List[Metrics], Metrics, Metrics]:
        tr = [self.run_range(None, f.train_start, f.train_end, default_mode=True) for f in self.folds]
        te = [self.run_range(None, f.test_start, f.test_end, default_mode=True) for f in self.folds]
        return tr, te, aggregate(tr), aggregate(te)


def lhs_configs(n: int, seed: int) -> List[Config]:
    if n <= 0:
        return []
    lows = np.array([BOUNDS[k][0] for k in PARAM_KEYS], dtype=float)
    highs = np.array([BOUNDS[k][1] for k in PARAM_KEYS], dtype=float)
    if qmc is not None:
        raw = qmc.LatinHypercube(d=len(PARAM_KEYS), seed=seed).random(n=n)
    else:
        raw = np.random.default_rng(seed).random((n, len(PARAM_KEYS)))
    scaled = lows + raw * (highs - lows)
    return [Config.from_dict({k: float(v) for k, v in zip(PARAM_KEYS, row)}) for row in scaled]


def grid_configs(n: int, seed: int) -> List[Config]:
    if n <= 0:
        return []
    rng = random.Random(seed)
    seen = set()
    out = []
    attempts = 0
    while len(out) < n and attempts < n * 30:
        attempts += 1
        cfg = Config.from_dict({k: rng.choice(list(GRID[k])) for k in PARAM_KEYS})
        k = cfg.key()
        if k in seen:
            continue
        seen.add(k)
        out.append(cfg)
    return out


def eval_phase(name: str, cfgs: Sequence[Config], opt: Optimizer) -> List[Eval]:
    out = []
    total = len(cfgs)
    best_obj = -1e18
    t0 = _time.time()
    log_every = max(1, total // 20)  # ~5% increments
    for i, cfg in enumerate(cfgs, start=1):
        e = opt.evaluate(cfg, name)
        out.append(e)
        if e.obj > best_obj:
            best_obj = e.obj
        if i % log_every == 0 or i == total:
            print(_progress_line(name, i, total, t0, best_obj))
    elapsed = _time.time() - t0
    print(f"[{name}] completed {total} trials in {_fmt_duration(elapsed)}")
    return out


def evals_df(evals: Sequence[Eval]) -> pd.DataFrame:
    if not evals:
        return pd.DataFrame()
    df = pd.DataFrame([e.row() for e in evals])
    return df.sort_values("objective_score", ascending=False).reset_index(drop=True)


def dedupe_evals(evals: Iterable[Eval]) -> List[Eval]:
    best: Dict[Tuple[float, ...], Eval] = {}
    for e in evals:
        k = e.cfg.key()
        if k not in best or e.obj > best[k].obj:
            best[k] = e
    return list(best.values())


def tpe_phase(opt: Optimizer, trials: int, seed: int, warm_start: Sequence[Config]) -> List[Eval]:
    if trials <= 0:
        return []
    rows: List[Eval] = []
    t0 = _time.time()
    best_obj = -1e18
    log_every = max(1, trials // 20)
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    for cfg in warm_start:
        study.enqueue_trial(cfg.as_dict())

    def objective(trial: optuna.Trial) -> float:
        nonlocal best_obj
        cfg = Config.from_dict(
            {
                "structural": trial.suggest_float("structural", *BOUNDS["structural"]),
                "shortterm": trial.suggest_float("shortterm", *BOUNDS["shortterm"]),
                "intraday": trial.suggest_float("intraday", *BOUNDS["intraday"]),
                "breadth": trial.suggest_float("breadth", *BOUNDS["breadth"]),
                "nifty": trial.suggest_float("nifty", *BOUNDS["nifty"]),
                "threshold": trial.suggest_float("threshold", *BOUNDS["threshold"]),
            }
        )
        e = opt.evaluate(cfg, "tpe")
        rows.append(e)
        if e.obj > best_obj:
            best_obj = e.obj
        i = len(rows)
        if i % log_every == 0 or i == trials:
            print(_progress_line("tpe", i, trials, t0, best_obj))
        return e.obj

    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    elapsed = _time.time() - t0
    print(f"[tpe] completed {trials} trials in {_fmt_duration(elapsed)}")
    return rows


def nsga_phase(opt: Optimizer, trials: int, seed: int) -> List[Eval]:
    if trials <= 0:
        return []
    rows: List[Eval] = []
    t0 = _time.time()
    log_every = max(1, trials // 20)
    study = optuna.create_study(
        directions=["maximize", "minimize", "maximize", "maximize"],
        sampler=optuna.samplers.NSGAIISampler(seed=seed),
    )

    def objective(trial: optuna.Trial) -> Tuple[float, float, float, float]:
        cfg = Config.from_dict(
            {
                "structural": trial.suggest_float("structural", *BOUNDS["structural"]),
                "shortterm": trial.suggest_float("shortterm", *BOUNDS["shortterm"]),
                "intraday": trial.suggest_float("intraday", *BOUNDS["intraday"]),
                "breadth": trial.suggest_float("breadth", *BOUNDS["breadth"]),
                "nifty": trial.suggest_float("nifty", *BOUNDS["nifty"]),
                "threshold": trial.suggest_float("threshold", *BOUNDS["threshold"]),
            }
        )
        e = opt.evaluate(cfg, "nsga2")
        rows.append(e)
        i = len(rows)
        if i % log_every == 0 or i == trials:
            print(_progress_line("nsga2", i, trials, t0))
        return e.test.return_pct, e.test.drawdown_pct, min(e.test.profit_factor, 5.0), e.test.expectancy

    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    elapsed = _time.time() - t0
    print(f"[nsga2] completed {trials} trials in {_fmt_duration(elapsed)}")
    return rows


def load_hurdles(path: Optional[Path]) -> Dict[str, float]:
    if path is None:
        return dict(DEFAULT_HURDLES)
    p = json.loads(path.read_text(encoding="utf-8"))
    return {
        "return_pct": float(p.get("equity_analysis", {}).get("total_return_pct", DEFAULT_HURDLES["return_pct"])),
        "max_drawdown_pct": float(p.get("equity_analysis", {}).get("max_drawdown_pct", DEFAULT_HURDLES["max_drawdown_pct"])),
        "profit_factor": float(p.get("trade_statistics", {}).get("profit_factor", DEFAULT_HURDLES["profit_factor"])),
        "win_rate_pct": float(p.get("trade_statistics", {}).get("win_rate_pct", DEFAULT_HURDLES["win_rate_pct"])),
        "expectancy": float(p.get("trade_statistics", {}).get("avg_trade_pnl", DEFAULT_HURDLES["expectancy"])),
    }


def fold_beats(c: Metrics, b: Metrics) -> bool:
    return (
        c.return_pct > b.return_pct
        and c.drawdown_pct <= b.drawdown_pct
        and c.profit_factor > b.profit_factor
        and (c.win_rate_pct >= b.win_rate_pct or c.expectancy >= b.expectancy)
    )


def absolute_pass(c: Metrics, h: Dict[str, float]) -> bool:
    return (
        c.return_pct > h["return_pct"]
        and c.drawdown_pct <= h["max_drawdown_pct"]
        and c.profit_factor > h["profit_factor"]
        and c.expectancy > h["expectancy"]
        and (c.win_rate_pct >= h["win_rate_pct"] or c.expectancy > h["expectancy"])
    )


def bootstrap_ci(vals: Sequence[float], seed: int, n_boot: int = 2000) -> Tuple[float, float]:
    arr = np.array(list(vals), dtype=float)
    if arr.size == 0:
        return 0.0, 0.0
    rng = np.random.default_rng(seed)
    n = arr.size
    sims = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sims.append(float(np.mean(arr[idx])))
    return float(np.quantile(sims, 0.025)), float(np.quantile(sims, 0.975))


def nested_selection(opt: Optimizer, cands: Sequence[Eval]) -> Dict[str, Any]:
    rows = []
    selected: List[Metrics] = []
    counts = Counter()
    total_folds = len(opt.folds)
    t0 = _time.time()
    for fi, f in enumerate(opt.folds, 1):
        best_cfg = None
        best_score = -1e18
        for c in cands:
            tr_m = opt.run_range(c.cfg, f.train_start, f.train_end, default_mode=False)
            s = score_base(tr_m)
            if s > best_score:
                best_score = s
                best_cfg = c.cfg
        if best_cfg is None:
            continue
        te_m = opt.run_range(best_cfg, f.test_start, f.test_end, default_mode=False)
        selected.append(te_m)
        counts[str(best_cfg.key())] += 1
        rows.append(
            {
                "fold_id": f.fold_id,
                "train_start": f.train_start.isoformat(),
                "train_end": f.train_end.isoformat(),
                "test_start": f.test_start.isoformat(),
                "test_end": f.test_end.isoformat(),
                "selected_params": best_cfg.as_dict(),
                "train_inner_score": best_score,
                "test_metrics": te_m.__dict__,
            }
        )
        print(f"  [nested WF] fold {fi}/{total_folds} done ({_fmt_duration(_time.time() - t0)} elapsed)")
    print(f"  [nested WF] completed in {_fmt_duration(_time.time() - t0)}")
    return {
        "fold_rows": rows,
        "selected_config_frequency": dict(counts),
        "aggregated_oos_metrics": aggregate(selected).__dict__,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="V6.2 weight optimization")
    p.add_argument("--data-root", type=str, default="data")
    p.add_argument("--start-date", type=str, default="2025-03-01")
    p.add_argument("--end-date", type=str, default="2025-12-31")
    p.add_argument("--train-months", type=int, default=4)
    p.add_argument("--test-months", type=int, default=1)
    p.add_argument("--min-folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--discrete-trials", type=int, default=64)
    p.add_argument("--coarse-trials", type=int, default=120)
    p.add_argument("--tpe-trials", type=int, default=240)
    p.add_argument("--nsga-trials", type=int, default=180)
    p.add_argument("--shortlist-from-each", type=int, default=25)
    p.add_argument("--shortlist-size", type=int, default=30)
    p.add_argument("--min-trades", type=int, default=350)
    p.add_argument("--min-total-trades", type=int, default=700)
    p.add_argument("--conc-limit", type=float, default=0.55)
    p.add_argument("--max-overfit-gap", type=float, default=0.12)
    p.add_argument("--spread-bps", type=float, default=6.0)
    p.add_argument("--circuit-pct", type=float, default=0.10)
    p.add_argument("--baseline-analysis-json", type=str, default=None)
    p.add_argument("--results-dir", type=str, default="results")
    p.add_argument("--no-precompute", action="store_true",
                   help="Disable indicator pre-computation (slower, uses lazy cache)")
    p.add_argument("--workers", type=int, default=1,
                   help="Parallel workers for trial evaluation (default=1, single-process)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    root = Path(__file__).resolve().parent
    cwd = Path.cwd()
    data_root = Path(args.data_root)
    if data_root.is_absolute():
        data_root = data_root.resolve()
    else:
        data_root = (cwd / data_root).resolve() if (cwd / data_root).exists() else (root / data_root).resolve()

    folds = build_folds(start, end, args.train_months, args.test_months)
    if len(folds) < args.min_folds:
        raise RuntimeError(f"Need at least {args.min_folds} folds, got {len(folds)}")

    baseline_path = Path(args.baseline_analysis_json) if args.baseline_analysis_json else None
    hurdles = load_hurdles(baseline_path)

    out_root = Path(args.results_dir)
    if out_root.is_absolute():
        out_root = out_root.resolve()
    else:
        out_root = (cwd / out_root).resolve()
    run_dir = out_root / f"weight_opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    total_trials = args.discrete_trials + args.coarse_trials + args.tpe_trials + args.nsga_trials
    gpu_tag = "CuPy GPU" if HAS_CUPY else "CPU"
    precomp_tag = "ON" if not args.no_precompute else "OFF"
    print(f"Results: {run_dir}")
    print(f"Folds: {len(folds)}  |  Total trials planned: {total_trials}")
    print(f"Acceleration: precompute={precomp_tag}  |  backend={gpu_tag}  |  workers={args.workers}")
    print("=" * 70)

    pipeline_t0 = _time.time()
    phase_times: List[Tuple[str, float]] = []

    opt = Optimizer(
        data_root=data_root,
        folds=folds,
        min_trades=args.min_trades,
        conc_limit=args.conc_limit,
        spread_bps=args.spread_bps,
        circuit_pct=args.circuit_pct,
        precompute=not args.no_precompute,
        global_start=start,
        global_end=end,
    )

    # ── Baseline ──
    print("\n[1/6] Baseline evaluation...")
    t0 = _time.time()
    _, base_fold_test, _, base_test_agg = opt.evaluate_default()
    pd.DataFrame([m.__dict__ for m in base_fold_test]).to_csv(run_dir / "baseline_fold_test.csv", index=False)
    phase_times.append(("Baseline", _time.time() - t0))
    print(f"  Baseline done in {_fmt_duration(phase_times[-1][1])}  |  "
          f"OOS Return={base_test_agg.return_pct:+.2f}%  DD={base_test_agg.drawdown_pct:.2f}%")

    # ── Discrete ──
    print(f"\n[2/6] Discrete phase ({args.discrete_trials} trials)...")
    t0 = _time.time()
    discrete = eval_phase("discrete", grid_configs(args.discrete_trials, args.seed), opt)
    evals_df(discrete).to_csv(run_dir / "phase_discrete.csv", index=False)
    phase_times.append(("Discrete", _time.time() - t0))

    # ── Coarse LHS ──
    print(f"\n[3/6] Coarse LHS phase ({args.coarse_trials} trials)...")
    t0 = _time.time()
    coarse = eval_phase("coarse_lhs", lhs_configs(args.coarse_trials, args.seed + 11), opt)
    evals_df(coarse).to_csv(run_dir / "phase_coarse_lhs.csv", index=False)
    phase_times.append(("Coarse LHS", _time.time() - t0))

    warm = [e.cfg for e in sorted(dedupe_evals(discrete + coarse), key=lambda x: x.obj, reverse=True)[:30]]

    # ── TPE ──
    print(f"\n[4/6] TPE Bayesian phase ({args.tpe_trials} trials)...")
    t0 = _time.time()
    tpe = tpe_phase(opt, args.tpe_trials, args.seed + 29, warm)
    evals_df(tpe).to_csv(run_dir / "phase_tpe.csv", index=False)
    phase_times.append(("TPE", _time.time() - t0))

    # ── NSGA-II ──
    print(f"\n[5/6] NSGA-II multi-objective phase ({args.nsga_trials} trials)...")
    t0 = _time.time()
    nsga = nsga_phase(opt, args.nsga_trials, args.seed + 47)
    evals_df(nsga).to_csv(run_dir / "phase_nsga2.csv", index=False)
    phase_times.append(("NSGA-II", _time.time() - t0))

    # ── Shortlist + Ranking ──
    print(f"\n[6/6] Shortlisting & deployment ranking...")
    t0 = _time.time()
    merged = []
    for group in (discrete, coarse, tpe, nsga):
        merged.extend(sorted(group, key=lambda x: x.obj, reverse=True)[: args.shortlist_from_each])
    shortlist = sorted(dedupe_evals(merged), key=lambda x: x.obj, reverse=True)[: args.shortlist_size]
    evals_df(shortlist).to_csv(run_dir / "shortlist.csv", index=False)

    rank_rows = []
    for c in shortlist:
        n = min(len(c.fold_test), len(base_fold_test))
        beats = sum(1 for i in range(n) if fold_beats(c.fold_test[i], base_fold_test[i]))
        majority = beats > n / 2 if n > 0 else False
        abs_ok = absolute_pass(c.test, hurdles)
        overfit_ok = c.overfit_gap <= args.max_overfit_gap
        trades_ok = c.test.trades >= args.min_total_trades
        eligible = majority and abs_ok and overfit_ok and trades_ok
        row = c.row()
        row.update(
            {
                "beats_default_oos_folds": beats,
                "total_oos_folds": n,
                "beats_fold_majority": majority,
                "beats_absolute_hurdles": abs_ok,
                "overfit_ok": overfit_ok,
                "trade_count_ok": trades_ok,
                "eligible_for_deploy": eligible,
            }
        )
        rank_rows.append(row)

    rank_df = pd.DataFrame(rank_rows).sort_values(
        ["eligible_for_deploy", "beats_default_oos_folds", "objective_score", "sparsity_near_zero"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    rank_df.to_csv(run_dir / "deployment_ranking.csv", index=False)

    if rank_df.empty:
        return 1
    top = rank_df.iloc[0].to_dict()
    top_cfg = Config.from_dict(
        {
            "structural": top["w_structural"],
            "shortterm": top["w_shortterm"],
            "intraday": top["w_intraday"],
            "breadth": top["w_breadth"],
            "nifty": top["w_nifty"],
            "threshold": top["bias_threshold"],
        }
    )
    top_eval = next((e for e in shortlist if e.cfg.key() == top_cfg.key()), None)

    nested = nested_selection(opt, shortlist[: min(20, len(shortlist))])
    Path(run_dir / "nested_walk_forward.json").write_text(json.dumps(nested, indent=2), encoding="utf-8")

    if top_eval:
        c_ret = [m.return_pct for m in top_eval.fold_test]
        c_dd = [m.drawdown_pct for m in top_eval.fold_test]
        b_ret = [m.return_pct for m in base_fold_test]
        b_dd = [m.drawdown_pct for m in base_fold_test]
        n = min(len(c_ret), len(b_ret))
        stats = {
            "bootstrap_return_ci95": dict(zip(["low", "high"], bootstrap_ci(c_ret, args.seed))),
            "bootstrap_drawdown_ci95": dict(zip(["low", "high"], bootstrap_ci(c_dd, args.seed + 7))),
            "paired_fold_mean_return_diff_pct": float(np.mean([c_ret[i] - b_ret[i] for i in range(n)])) if n else 0.0,
            "paired_fold_mean_drawdown_improvement_pct": float(np.mean([b_dd[i] - c_dd[i] for i in range(n)])) if n else 0.0,
        }
    else:
        stats = {}

    summary = {
        "selected_params": top_cfg.as_dict(),
        "selected_row": top,
        "baseline_hurdles": hurdles,
        "baseline_oos_aggregate": base_test_agg.__dict__,
        "statistical_checks": stats,
    }
    Path(run_dir / "best_candidate_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    Path(run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "data_root": str(data_root),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "folds": [f.__dict__ for f in folds],
                "args": vars(args),
                "baseline_hurdles": hurdles,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    phase_times.append(("Ranking & Nested WF", _time.time() - t0))

    # ── Final Summary ──
    total_elapsed = _time.time() - pipeline_t0
    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"\nTotal wall time: {_fmt_duration(total_elapsed)}")
    print(f"Range-level cache: {len(opt.cache)} unique (config, date-range) evaluations")
    ind_cache_size = len(opt.engine._ind_cache)
    trail_cache_size = len(opt.engine._trail_cache)
    if ind_cache_size:
        print(f"Indicator cache: {ind_cache_size:,} entries  |  Trail cache: {trail_cache_size:,} entries")
    print(f"\nPhase Timing Breakdown:")
    for name, dur in phase_times:
        pct = dur / total_elapsed * 100 if total_elapsed > 0 else 0
        print(f"  {name:<22s}  {_fmt_duration(dur):>12s}  ({pct:5.1f}%)")
    print(f"  {'─' * 22}  {'─' * 12}  {'─' * 7}")
    print(f"  {'TOTAL':<22s}  {_fmt_duration(total_elapsed):>12s}")
    print(f"\nTop params: {top_cfg.as_dict()}")
    print(
        f"OOS return={top['oos_return_pct']:.2f}% "
        f"DD={top['oos_drawdown_pct']:.2f}% "
        f"PF={top['oos_pf']:.3f} "
        f"Expectancy={top['oos_expectancy']:.2f} "
        f"Eligible={bool(top['eligible_for_deploy'])}"
    )
    print(f"\nResults saved to: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
