"""
================================================================================
V4 INDICATORS MODULE
================================================================================
High-performance, stateless math functions for technical indicators.
Strictly adheres to 04.concepts version 3.0.

Included:
- WMA (Weighted Moving Average)
- HMA (Hull Moving Average)
- ATR (Average True Range)
- RSI & StochRSI
- RVOL (Relative Volume)
- RS (Relative Strength - Subtraction Method)

Author: Sector Analysis System
Version: 4.0.0
================================================================================
"""

import numpy as np
from typing import List, Optional, Tuple, Union


# ══════════════════════════════════════════════════════════════════════════════
# MOVING AVERAGES
# ══════════════════════════════════════════════════════════════════════════════

def calculate_wma(data: np.ndarray, period: int) -> float:
    """
    Calculate Weighted Moving Average for the last 'period' elements.
    WMA = sum(price_i * weight_i) / sum(weights)
    """
    if len(data) < period:
        return 0.0
    
    weights = np.arange(1, period + 1)
    weight_sum = weights.sum()
    if weight_sum == 0:
        return 0.0
    return float(np.dot(data[-period:], weights) / weight_sum)


def calculate_hma(prices: Union[List[float], np.ndarray], period: int) -> float:
    """
    Calculate Hull Moving Average.
    HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    """
    prices = np.array(prices)
    if len(prices) < period:
        return 0.0

    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    # To calculate HMA properly, we need a series of the raw (2*WMA(n/2) - WMA(n))
    # We calculate this series for the last 'sqrt_period' to then WMA it.
    raw_hma_series = []
    
    # We need enough lookback to calculate WMAs for the final WMA smoothing
    for i in range(sqrt_period):
        end_idx = len(prices) - i
        if end_idx < period:
            break
        
        subset = prices[:end_idx]
        wma_half = calculate_wma(subset, half_period)
        wma_full = calculate_wma(subset, period)
        
        raw_hma_series.insert(0, 2 * wma_half - wma_full)

    if len(raw_hma_series) < sqrt_period:
        return raw_hma_series[-1] if raw_hma_series else 0.0

    return calculate_wma(np.array(raw_hma_series), sqrt_period)


# ══════════════════════════════════════════════════════════════════════════════
# VOLATILITY
# ══════════════════════════════════════════════════════════════════════════════

def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 10) -> float:
    """
    Calculate Average True Range (SMA of True Range).
    TR = max(H-L, abs(H-PC), abs(L-PC))
    """
    if len(closes) < period + 1:
        return 0.0

    # Calculate True Ranges
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    
    # ATR is SMA of TR
    return float(np.mean(tr_list[-period:]))


# ══════════════════════════════════════════════════════════════════════════════
# MOMENTUM
# ══════════════════════════════════════════════════════════════════════════════

def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
    """Standard RSI calculation."""
    if len(closes) < period + 1:
        return 50.0
    
    deltas = np.diff(closes)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    if down == 0:
        rs = 100.0
    else:
        rs = up / down
    
    rsi = np.zeros_like(closes)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(closes)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period

        if down == 0:
            rs = 100.0
        else:
            rs = up / down
        rsi[i] = 100. - 100. / (1. + rs)

    return float(rsi[-1])


def calculate_stoch_rsi(closes: Union[List[float], np.ndarray], 
                        rsi_period: int = 14, 
                        stoch_period: int = 14, 
                        k_smooth: int = 3, 
                        d_smooth: int = 3) -> Tuple[float, float]:
    """
    Calculate Stochastic RSI (K, D).
    Values in range 0-100.
    """
    closes = np.array(closes)
    # 1. We need a series of RSI values
    # To smooth K and D, we need extra RSI history
    total_needed = stoch_period + k_smooth + d_smooth + 5
    rsi_series = []
    
    for i in range(total_needed):
        end_idx = len(closes) - i
        if end_idx < rsi_period + 1:
            break
        rsi_series.insert(0, calculate_rsi(closes[:end_idx], rsi_period))
    
    if len(rsi_series) < stoch_period:
        return 50.0, 50.0

    # 2. Calculate Raw StochRSI
    stoch_raw = []
    for i in range(len(rsi_series) - stoch_period + 1):
        window = rsi_series[i : i + stoch_period]
        low = min(window)
        high = max(window)
        curr = window[-1]
        
        if high == low:
            stoch_raw.append(50.0)
        else:
            stoch_raw.append(((curr - low) / (high - low)) * 100)
            
    # 3. Calculate Smooth %K (SMA of raw)
    k_series = []
    for i in range(len(stoch_raw) - k_smooth + 1):
        k_series.append(np.mean(stoch_raw[i : i + k_smooth]))
        
    if not k_series:
        return 50.0, 50.0
        
    # 4. Calculate Smooth %D (SMA of K)
    d = np.mean(k_series[-d_smooth:])
    k = k_series[-1]
    
    return float(k), float(d)


# ══════════════════════════════════════════════════════════════════════════════
# VOLUME & RELATIVE STRENGTH
# ══════════════════════════════════════════════════════════════════════════════

def calculate_rvol(current_vol: int, avg_vol: float) -> float:
    """Calculate Relative Volume."""
    if avg_vol <= 0:
        return 0.0
    return float(current_vol / avg_vol)


def calculate_rs_subtraction(subject_return: float, benchmark_return: float) -> float:
    """
    Relative Strength using subtraction method.
    RS = Subject % - Benchmark %
    """
    return subject_return - benchmark_return


def calculate_return_pct(current: float, previous: float) -> float:
    """Simple percentage return calculation."""
    if previous <= 0:
        return 0.0
    return ((current - previous) / previous) * 100


def calculate_slope(current: float, previous: float, threshold: float = 0.0001) -> str:
    """Determine slope direction: UP, DOWN, or FLAT."""
    if not current or not previous:
        return "FLAT"
    
    diff = current - previous
    if diff > threshold:
        return "UP"
    elif diff < -threshold:
        return "DOWN"
    else:
        return "FLAT"
