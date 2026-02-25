"""
GPU-accelerated indicator pre-computation for V6.2 optimization.

Pre-computes ALL weight-independent indicators for every (stock, 5m-bar) pair
before the optimization loop starts.  Subsequent backtest runs become pure
dictionary lookups (O(1) per indicator per bar) instead of recomputing expensive
HMA / StochRSI / ATR each time.

Acceleration tiers:
  1. CuPy (GPU)   – batch-vectorized series computation on Colab T4
  2. NumPy (CPU)   – vectorized fallback on machines without GPU
  3. Lazy memoize  – indicators cached on first encounter (no upfront pass)

Tier 1+2 are used by `precompute_all()`; tier 3 is built into the engine's
_scan_tradeable_stocks via _ind_cache.
"""

from __future__ import annotations

import time as _time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import cupy as cp          # type: ignore[import-untyped]
    HAS_CUPY = True
except ImportError:
    cp = None
    HAS_CUPY = False

try:
    from .indicators import (
        calculate_atr,
        calculate_hma,
        calculate_rvol,
        calculate_slope,
        calculate_stoch_rsi,
    )
    from .v6lite.brain import ExecutionFilters
except ImportError:
    from indicators import (
        calculate_atr,
        calculate_hma,
        calculate_rvol,
        calculate_slope,
        calculate_stoch_rsi,
    )
    from v6lite.brain import ExecutionFilters

# ---------------------------------------------------------------------------
# GPU / vectorised rolling helpers
# ---------------------------------------------------------------------------

def _xp():
    """Return the array module: cupy if available, else numpy."""
    return cp if HAS_CUPY else np


def rolling_atr_series(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                       period: int = 14) -> np.ndarray:
    """Vectorised rolling ATR for the full series.

    Returns an array of length len(closes).  Positions with insufficient
    look-back are filled with 0.0.
    """
    xp = _xp()
    h = xp.asarray(highs, dtype=xp.float64)
    l = xp.asarray(lows, dtype=xp.float64)
    c = xp.asarray(closes, dtype=xp.float64)

    n = len(c)
    if n < period + 1:
        out = xp.zeros(n, dtype=xp.float64)
        return out.get() if HAS_CUPY else out

    # True-range series (starts at index-1 in close array)
    tr = xp.maximum(
        h[1:] - l[1:],
        xp.maximum(xp.abs(h[1:] - c[:-1]),
                   xp.abs(l[1:] - c[:-1]))
    )

    # Rolling mean via cumulative sum  (O(N), no Python loop)
    cs = xp.cumsum(tr)
    padded = xp.concatenate([xp.zeros(1, dtype=xp.float64), cs])
    rolling = (padded[period:] - padded[:-period]) / period

    # rolling[i] = ATR at position (i + period) in TR array
    #           = ATR for close index (i + period + 1)
    # But our simple mean ATR matches the scalar `calculate_atr` signature:
    # calculate_atr(..., period) = mean(tr[-period:])
    # At close-index j (j >= period+1): rolling[j - period - 1]
    out = xp.zeros(n, dtype=xp.float64)
    start = period + 1          # first close-index with enough data (period TR values)
    end = start + len(rolling)
    valid = min(end, n) - start
    if valid > 0:
        out[start:start + valid] = rolling[:valid]

    return out.get() if HAS_CUPY else np.asarray(out)


def rolling_rsi_series(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorised Wilder-smoothed RSI for the full series.

    Uses the same sequential Wilder smoothing as the scalar `calculate_rsi`
    but runs the entire loop on GPU (or NumPy) without per-element Python
    overhead.
    """
    xp = _xp()
    c = xp.asarray(closes, dtype=xp.float64)
    n = len(c)
    rsi = xp.full(n, 50.0, dtype=xp.float64)

    if n < period + 1:
        return rsi.get() if HAS_CUPY else np.asarray(rsi)

    deltas = xp.diff(c)
    ups = xp.where(deltas > 0, deltas, 0.0)
    dns = xp.where(deltas < 0, -deltas, 0.0)

    # Seed
    up_avg = float(xp.sum(ups[:period])) / period
    dn_avg = float(xp.sum(dns[:period])) / period

    # First RSI value
    rs = 100.0 if dn_avg == 0 else up_avg / dn_avg
    rsi_arr_np = np.full(n, 50.0)
    rsi_arr_np[period] = 100.0 - 100.0 / (1.0 + rs)

    ups_np = ups.get() if HAS_CUPY else np.asarray(ups)
    dns_np = dns.get() if HAS_CUPY else np.asarray(dns)

    # Sequential Wilder smoothing (must be serial, runs on CPU)
    for i in range(period, len(deltas)):
        up_avg = (up_avg * (period - 1) + float(ups_np[i])) / period
        dn_avg = (dn_avg * (period - 1) + float(dns_np[i])) / period
        rs = 100.0 if dn_avg == 0 else up_avg / dn_avg
        rsi_arr_np[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    return rsi_arr_np


# ---------------------------------------------------------------------------
# Pre-computation orchestrator
# ---------------------------------------------------------------------------

def _fmt(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    return f"{m}m {s:02d}s" if m else f"{secs:.1f}s"


def precompute_all(engine, global_start: date, global_end: date,
                   verbose: bool = True) -> int:
    """Pre-compute ALL weight-independent indicators and populate engine caches.

    Call this ONCE after `engine.initialize()` and before the optimisation loop.
    Returns the number of indicators cached.

    The heavy indicator functions (HMA, StochRSI, ATR) are computed for every
    (stock, 5-minute bar) in the date range.  Results are stored in
    ``engine._ind_cache`` and ``engine._trail_cache`` so that subsequent
    ``run_backtest`` calls skip all indicator maths.
    """
    if not engine.initialized:
        raise RuntimeError("Engine must be initialised before pre-computation.")

    t0 = _time.time()
    trading_days = engine._get_trading_days(global_start, global_end)
    all_stock_syms: List[str] = [stk["symbol"] for stk in engine.stocks]

    # Count total bars for progress reporting
    total_bars = 0
    bars_per_day: Dict[date, int] = {}
    for day in trading_days:
        nifty_day = engine._get_intraday_day("NIFTY 50", day)
        bars_per_day[day] = len(nifty_day)
        total_bars += len(nifty_day)
    engine._daily_before_cache.clear()
    engine._intraday_day_cache.clear()

    if verbose:
        backend = "CuPy (GPU)" if HAS_CUPY else "NumPy (CPU)"
        print(f"[precompute] backend={backend}  |  {len(trading_days)} days  "
              f"|  ~{total_bars} bars  |  {len(all_stock_syms)} stocks")

    # ----- pre-compute full 5m ATR series per stock (vectorised) -----
    atr5m_series: Dict[str, np.ndarray] = {}
    trail_atr_series: Dict[str, np.ndarray] = {}
    trail_high_series: Dict[str, np.ndarray] = {}
    trail_low_series: Dict[str, np.ndarray] = {}

    TRAIL_LOOKBACK = 10  # must match TRAIL_LOOKBACK_BARS in engine

    for sym in all_stock_syms:
        df = engine.intra_data.get(sym)
        if df is None or df.empty:
            continue
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)

        atr5m_series[sym] = rolling_atr_series(h, l, c, period=14)
        trail_atr_series[sym] = rolling_atr_series(h, l, c, period=TRAIL_LOOKBACK)

        # Rolling high / low anchors for chandelier
        n = len(h)
        rh = np.zeros(n, dtype=float)
        rl = np.zeros(n, dtype=float)
        if n >= TRAIL_LOOKBACK:
            for i in range(TRAIL_LOOKBACK - 1, n):
                rh[i] = float(h[i - TRAIL_LOOKBACK + 1: i + 1].max())
                rl[i] = float(l[i - TRAIL_LOOKBACK + 1: i + 1].min())
        trail_high_series[sym] = rh
        trail_low_series[sym] = rl

    if verbose:
        print(f"[precompute] vectorised 5m ATR + trail anchors: {_fmt(_time.time() - t0)}")

    # ----- iterate through every (day, bar, stock) -----
    cached = 0
    t_loop = _time.time()
    log_every = max(1, len(trading_days) // 10)

    for day_idx, day in enumerate(trading_days):
        baselines = engine._build_day_baselines(day)
        nifty_day = engine._get_intraday_day("NIFTY 50", day)
        day_ord = day.toordinal()

        # Per-stock daily indicators (computed once per day)
        daily_cache_day: Dict[str, Dict[str, Any]] = {}
        for sym in all_stock_syms:
            daily_hist = engine._get_daily_before(sym, day)
            if daily_hist is None or len(daily_hist) < 20:
                continue
            closes_d = daily_hist["close"].to_numpy(dtype=float)
            highs_d = daily_hist["high"].to_numpy(dtype=float)
            lows_d = daily_hist["low"].to_numpy(dtype=float)
            vols_d = daily_hist["volume"].to_numpy(dtype=float)
            adv = ExecutionFilters.calculate_adv_crores(closes_d, vols_d)
            atr_d = calculate_atr(highs_d, lows_d, closes_d, period=10)
            daily_cache_day[sym] = {
                "adv": adv,
                "atr": atr_d,
                "closes_d": closes_d,
            }

        # Iterate bars
        for ts in nifty_day.index:
            for sym in all_stock_syms:
                dc = daily_cache_day.get(sym)
                if dc is None:
                    engine._ind_cache[(sym, ts)] = None  # sentinel
                    continue

                row, intra_pos = engine._get_intra_row(sym, ts)
                if row is None:
                    engine._ind_cache[(sym, ts)] = None
                    continue

                curr_price = float(row["close"])
                atr = dc["atr"]
                adv = dc["adv"]

                # 5m ATR from pre-computed series
                atr_5m_val = 0.0
                atr5m_arr = atr5m_series.get(sym)
                if atr5m_arr is not None and intra_pos < len(atr5m_arr):
                    atr_5m_val = float(atr5m_arr[intra_pos])

                # Microstructure gate
                bid, ask, u_circuit, l_circuit = engine._synthetic_microstructure(
                    sym, curr_price, baselines)
                passed, gate_reason = ExecutionFilters.check_gate(
                    bid=bid, ask=ask, price=curr_price, atr=atr,
                    u_circuit=u_circuit, l_circuit=l_circuit)
                spread_atr = (ask - bid) / atr if atr > 0 else 1.0

                # HMA alignment
                daily_hist = engine._get_daily_before(sym, day)
                hma_align = engine._get_hma_alignment(
                    sym, curr_price, intra_pos, daily_hist)

                # StochRSI
                closes_d = dc["closes_d"]
                stoch_k, _ = calculate_stoch_rsi(
                    np.append(closes_d, curr_price))

                # RVOL
                rvol = engine._get_recent_rvol(sym, intra_pos)

                engine._ind_cache[(sym, ts)] = {
                    "intra_pos": intra_pos,
                    "curr_price": curr_price,
                    "adv": adv,
                    "atr": atr,
                    "atr_5m": atr_5m_val,
                    "gate_passed": passed,
                    "gate_reason": gate_reason,
                    "spread_atr": spread_atr,
                    "hma_align": hma_align,
                    "stoch_k": stoch_k,
                    "rvol": rvol,
                }

                # Trail cache (chandelier pre-data)
                t_atr_arr = trail_atr_series.get(sym)
                t_hi_arr = trail_high_series.get(sym)
                t_lo_arr = trail_low_series.get(sym)
                if (t_atr_arr is not None and intra_pos < len(t_atr_arr)
                        and t_hi_arr is not None and t_lo_arr is not None):
                    engine._trail_cache[(sym, intra_pos)] = (
                        float(t_atr_arr[intra_pos]),
                        float(t_hi_arr[intra_pos]),
                        float(t_lo_arr[intra_pos]),
                    )

                cached += 1

        # Free per-day DataFrame caches (memory)
        engine._daily_before_cache.clear()
        engine._intraday_day_cache.clear()

        if verbose and ((day_idx + 1) % log_every == 0 or day_idx + 1 == len(trading_days)):
            elapsed = _time.time() - t_loop
            pct = (day_idx + 1) / len(trading_days) * 100
            speed = cached / elapsed if elapsed > 0 else 0
            print(f"[precompute] {day_idx+1}/{len(trading_days)} days "
                  f"({pct:.0f}%)  |  {cached:,} cached  |  "
                  f"{speed:,.0f} ind/s  |  {_fmt(elapsed)}")

    total = _time.time() - t0
    if verbose:
        print(f"[precompute] DONE — {cached:,} indicators in {_fmt(total)}  "
              f"|  cache size {len(engine._ind_cache):,}")
    return cached
