"""Lightweight indicator utilities for backtest optimization (no broker deps)."""

from typing import List, Tuple, Union

import numpy as np


def calculate_wma(data: np.ndarray, period: int) -> float:
    if len(data) < period:
        return 0.0
    weights = np.arange(1, period + 1)
    weight_sum = weights.sum()
    if weight_sum == 0:
        return 0.0
    return float(np.dot(data[-period:], weights) / weight_sum)


def calculate_hma(prices: Union[List[float], np.ndarray], period: int) -> float:
    prices = np.array(prices)
    if len(prices) < period:
        return 0.0

    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    raw_hma_series = []
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


def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 10) -> float:
    if len(closes) < period + 1:
        return 0.0

    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    return float(np.mean(tr_list[-period:]))


def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    deltas = np.diff(closes)
    seed = deltas[: period + 1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    rs = 100.0 if down == 0 else up / down
    rsi = np.zeros_like(closes)
    rsi[:period] = 100.0 - 100.0 / (1.0 + rs)

    for i in range(period, len(closes)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.0
        else:
            upval = 0.0
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = 100.0 if down == 0 else up / down
        rsi[i] = 100.0 - 100.0 / (1.0 + rs)

    return float(rsi[-1])


def calculate_stoch_rsi(
    closes: Union[List[float], np.ndarray],
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> Tuple[float, float]:
    closes = np.array(closes)

    total_needed = stoch_period + k_smooth + d_smooth + 5
    rsi_series = []
    for i in range(total_needed):
        end_idx = len(closes) - i
        if end_idx < rsi_period + 1:
            break
        rsi_series.insert(0, calculate_rsi(closes[:end_idx], rsi_period))

    if len(rsi_series) < stoch_period:
        return 50.0, 50.0

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

    k_series = []
    for i in range(len(stoch_raw) - k_smooth + 1):
        k_series.append(float(np.mean(stoch_raw[i : i + k_smooth])))

    if not k_series:
        return 50.0, 50.0

    d = float(np.mean(k_series[-d_smooth:]))
    k = float(k_series[-1])
    return k, d


def calculate_rvol(current_vol: int, avg_vol: float) -> float:
    if avg_vol <= 0:
        return 0.0
    return float(current_vol / avg_vol)


def calculate_slope(current: float, previous: float, threshold: float = 0.0001) -> str:
    if not current or not previous:
        return "FLAT"

    diff = current - previous
    if diff > threshold:
        return "UP"
    if diff < -threshold:
        return "DOWN"
    return "FLAT"
