# V4 Backtest Engine - Optimization Plan

## Overview
This document outlines the optimization strategies to significantly reduce backtest execution time. Current execution is slow due to redundant calculations, inefficient loops, and lack of parallelization.

---

## Current Bottlenecks Analysis

### Performance Impact Matrix

| Bottleneck | Impact Level | Frequency | Current Complexity |
|------------|--------------|-----------|-------------------|
| Indicator recalculation | 🔴 High | Every 5-min candle | O(n_stocks × n_candles) |
| Sector breadth loops | 🔴 High | Every 5-min candle | O(n_sectors × n_constituents) |
| Single-threaded processing | 🟡 Medium | Entire run | Sequential execution |
| DataFrame filtering | 🟡 Medium | Every candle | Repeated df[df['date'] == ts] |
| VWAP calculation | 🟢 Low | Pre-loaded | N/A |

### Current Resource Usage
- **Iterations per day:** ~75,000+ (1000 stocks × 75 candles)
- **Estimated time:** 1-2 hours for 1 month of data
- **Memory usage:** High (all data loaded upfront)

---

## Optimization Strategies (Priority Order)

### Phase 1: Quick Wins (10-15x Speedup)

#### 1.1 Pre-compute Daily Indicators
**Problem:** Recalculates HMA9, HMA20, StochRSI every 5-minute candle
**Solution:** Calculate once at day start, update incrementally

```python
# Pre-compute at 09:20 (OR formation end)
daily_hma9 = calculate_hma(daily_closes[-20:], 9)
daily_hma20 = calculate_hma(daily_closes[-40:], 20)
daily_stoch_k = calculate_stoch_rsi(daily_closes)

# Update frequency:
# - HMA9: Every candle (fast calculation)
# - HMA20: Every 4 candles (20-min equivalent)
# - StochRSI: Every 14 candles
```

**Expected Speedup:** 5-10x for indicator calculations

---

#### 1.2 Reduced Scan Frequency
**Problem:** Scans every 5-minute candle (75 scans/day)
**Solution:** Only scan at key times

| Time Window | Scan Frequency | Scans/Day |
|-------------|----------------|-----------|
| 09:35 - 10:05 (ORB) | Every 15 min | 2-3 |
| 10:15 - 14:05 (MAIN) | Every 15 min | 16-18 |
| 14:05+ | No scans | 0 |

**Total Scans/Day:** ~20-25 instead of 75

**Expected Speedup:** 3x reduction in scan operations

---

#### 1.3 Vectorized Breadth Calculation
**Problem:** Python loop through each constituent
**Solution:** Use pandas vectorized operations

```python
# BEFORE (Slow - Python loop)
above = 0
below = 0
for s_sym in constituents:
    s_row = s_df[s_df['date'] == ts]
    if s_row.iloc[0]['close'] > s_row.iloc[0]['vwap']:
        above += 1
    elif s_row.iloc[0]['close'] < s_row.iloc[0]['vwap']:
        below += 1

# AFTER (Fast - Vectorized)
sector_candles = get_sector_candles_at_timestamp(sector, ts)
above = (sector_candles['close'] > sector_candles['vwap']).sum()
below = (sector_candles['close'] < sector_candles['vwap']).sum()
net_breadth = (above - below) / len(sector_candles)
```

**Expected Speedup:** 10-20x for breadth calculations

---

#### 1.4 Skip Non-Trading Windows
**Problem:** Full processing during GAP, EXIT_ONLY periods
**Solution:** Skip processing during non-entry windows

```python
def _should_scan(timestamp):
    playbook = get_playbook(timestamp.time())
    return playbook in ["ORB", "MAIN"]

# No sector scanning, no stock scanning, no indicator calculations
# Just update existing trades
```

**Expected Speedup:** Additional 1.5x during skip periods

---

### Phase 2: Advanced Optimizations (5-10x Additional Speedup)

#### 2.1 Numba JIT Compilation
**Problem:** Pure Python loops in indicator calculations
**Solution:** Use Numba for hot paths

```python
from numba import jit, prange

@jit(nopython=True, cache=True)
def calculate_atr_fast(highs, lows, closes, period=10):
    """Vectorized ATR with Numba acceleration."""
    n = len(closes)
    tr = np.zeros(n-1)
    for i in range(1, n):
        tr[i-1] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
    return np.mean(tr[-period:])

@jit(nopython=True, cache=True)
def calculate_hma_fast(data, period):
    """Vectorized HMA with Numba."""
    half = period // 2
    sqrt_period = int(np.sqrt(period))
    
    # WMA calculation
    weights = np.arange(1, half + 1)
    wma_half = np.convolve(data[-half:], weights / weights.sum())[-half:]
    
    weights = np.arange(1, period + 1)
    wma_full = np.convolve(data[-period:], weights / weights.sum())[-1]
    
    raw = 2 * wma_half - wma_full
    
    weights = np.arange(1, sqrt_period + 1)
    return np.convolve(raw, weights / weights.sum())[-1]
```

**Expected Speedup:** 10-50x for indicator functions

---

#### 2.2 Parallel Sector Processing
**Problem:** Sequential sector processing
**Solution:** Process sectors in parallel

```python
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing

def calculate_sector_score(args):
    sector_name, timestamp = args
    return compute_sector_metrics(sector_name, timestamp)

def process_all_sectors_parallel(timestamp, sectors):
    n_workers = min(multiprocessing.cpu_count(), len(sectors))
    
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        args_list = [(sec, timestamp) for sec in sectors]
        results = list(executor.map(calculate_sector_score, args_list))
    
    return results
```

**Expected Speedup:** 2-4x (CPU-bound, depends on cores)

---

#### 2.3 Optimized Data Access Pattern
**Problem:** Repeated DataFrame filtering
**Solution:** Use indexed lookups

```python
# BEFORE: Repeated filtering
for ts in timestamps:
    for sym in symbols:
        row = df[df['date'] == ts]  # Slow - O(n) scan

# AFTER: Pre-indexed lookup
df_indexed = df.set_index(['symbol', 'date'])
for ts in timestamps:
    for sym in symbols:
        row = df_indexed.loc[(sym, ts)]  # O(1) lookup
```

**Expected Speedup:** 3-5x for data access

---

### Phase 3: Architecture Changes (3-5x Additional Speedup)

#### 3.1 DuckDB for Data Storage
**Problem:** Pandas read_parquet per stock
**Solution:** Single DuckDB query for all data

```python
import duckdb

# Create a unified database
con = duckdb.connect('backtest_data.duckdb')

# Register all parquet files
con.execute("""
    CREATE TABLE daily_data AS 
    SELECT * FROM parquet_scan('data/daily/**/*.parquet')
""")

con.execute("""
    CREATE TABLE intra_data AS 
    SELECT * FROM parquet_scan('data/5minute/**/*.parquet')
""")

# Single query for all sector data at a timestamp
sector_data = con.execute("""
    SELECT 
        s.symbol,
        s.name as sector_name,
        d.close as daily_close,
        i.close as intra_close,
        i.vwap
    FROM sector_map s
    JOIN intra_data i ON i.symbol = s.symbol
    WHERE i.date = ?
    LIMIT 10000
""", [timestamp]).df()
```

**Expected Speedup:** 3-5x for data loading

---

#### 3.2 Lazy Data Loading
**Problem:** All stocks loaded at startup
**Solution:** Load only needed data on demand

```python
class LazyDataManager:
    def __init__(self):
        self.cache = {}
        self.max_cache_days = 30
    
    def get_daily_data(self, symbol, date_range):
        cache_key = f"daily_{symbol}_{date_range[0]}"
        if cache_key not in self.cache:
            # Load from disk only when needed
            self.cache[cache_key] = load_parquet(f"data/daily/{symbol}.parquet")
        return self.cache[cache_key]
    
    def cleanup_expired(self):
        """Remove cache entries older than max_cache_days"""
        pass
```

**Expected Speedup:** Faster startup, lower memory footprint

---

#### 3.3 Caching Layer
**Problem:** Repeated calculations for same data
**Solution:** LRU cache for expensive operations

```python
from functools import lru_cache
import hashlib

def cache_key(*args, **kwargs):
    """Generate cache key from arguments"""
    key_str = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()

@lru_cache(maxsize=10000)
def calculate_indicator_cached(indicator_name, symbol, timestamp, period):
    """Cached indicator calculation."""
    data = get_stock_data(symbol)
    return compute_indicator(indicator_name, data, period)
```

**Expected Speedup:** Near-instant for repeated calculations

---

## Implementation Roadmap

| Phase | Changes | Expected Speedup | Effort |
|-------|---------|------------------|--------|
| **Phase 1** | Pre-compute indicators + Reduced scan frequency + Vectorized breadth | 10-15x | 2-3 hours |
| **Phase 2** | Numba JIT + Parallel processing | 5-10x | 4-6 hours |
| **Phase 3** | DuckDB + Lazy loading | 3-5x | 6-8 hours |

**Overall Target:** 100-300x faster (2 hours → 1-5 minutes)

---

## Phase 1 Implementation Details

### Task 1.1: Add Scan Timestamps Configuration

**File:** `core_v4/config_v4.py`

```python
# Add new constants
SCAN_INTERVAL_ORB = 15  # minutes
SCAN_INTERVAL_MAIN = 15  # minutes
SCAN_START_ORB = time(9, 35)
SCAN_END_ORB = time(10, 5)
SCAN_START_MAIN = time(10, 15)
SCAN_END_MAIN = time(14, 5)
```

---

### Task 1.2: Pre-compute Daily Indicators

**File:** `backtest_v4/sector_engine_v4.3.py`

```python
class SectorBacktester:
    def __init__(self, data_root: Path):
        # ... existing code ...
        
        # New: Indicator cache
        self.daily_indicators: Dict[str, Dict] = {}
    
    def _precompute_daily_indicators(self, target_date, symbols):
        """Pre-compute indicators for all symbols at day start."""
        for sym in symbols:
            d_df = self.daily_data.get(sym)
            if d_df is None or d_df.empty:
                continue
            
            d_hist = d_df[d_df['date'].dt.date < target_date]
            if len(d_hist) < 40:
                continue
            
            closes = d_hist['close'].values
            self.daily_indicators[sym] = {
                'hma9': ind.calculate_hma(closes, 9),
                'hma20': ind.calculate_hma(closes, 20),
                'stoch_k': ind.calculate_stoch_rsi(closes)[0],
                'atr': ind.calculate_atr(
                    d_hist['high'].values,
                    d_hist['low'].values,
                    d_hist['close'].values,
                    10
                )
            }
```

---

### Task 1.3: Add Scan Frequency Check

**File:** `backtest_v4/sector_engine_v4.3.py`

```python
def _should_scan(self, timestamp: datetime) -> bool:
    """Check if we should scan at this timestamp."""
    t = timestamp.time()
    playbook = self._get_playbook(t)
    
    if playbook not in ["ORB", "MAIN"]:
        return False
    
    # ORB window: 09:35 - 10:05, scan every 15 min
    if playbook == "ORB":
        minute = t.hour * 60 + t.minute
        scan_minutes = [35, 50, 65]  # 09:35, 09:50, 10:05
        return any(abs(minute - sm) < 7 for sm in scan_minutes)
    
    # MAIN window: 10:15 - 14:05, scan every 15 min
    if playbook == "MAIN":
        minute = t.hour * 60 + t.minute
        scan_minutes = list(range(15, 14*60 + 5, 15))
        return any(abs(minute - sm) < 7 for sm in scan_minutes)
    
    return False
```

---

### Task 1.4: Vectorized Breadth Calculation

**File:** `backtest_v4/sector_engine_v4.3.py`

```python
def _calculate_breadth_vectorized(self, sector_name: str, timestamp: datetime) -> float:
    """Calculate net breadth using vectorized operations."""
    constituents = self.sector_map.get(sector_name, [])
    
    # Collect all candles at this timestamp
    closes = []
    vwaps = []
    
    for s_sym in constituents:
        i_df = self.intra_data.get(s_sym)
        if i_df is None:
            continue
        row = i_df[i_df['date'] == timestamp]
        if row.empty:
            continue
        closes.append(row.iloc[0]['close'])
        vwaps.append(row.iloc[0]['vwap'])
    
    if not closes:
        return 0.0
    
    closes_arr = np.array(closes)
    vwaps_arr = np.array(vwaps)
    
    # Vectorized comparison
    above = np.sum(closes_arr > vwaps_arr)
    below = np.sum(closes_arr < vwaps_arr)
    total = len(closes_arr)
    
    return (above - below) / total if total > 0 else 0.0
```

---

## Metrics to Track

| Metric | Current | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|--------|---------|----------------|----------------|----------------|
| Backtest time (1 month) | ~2 hours | ~10 minutes | ~3 minutes | ~1 minute |
| Memory usage | ~4 GB | ~2 GB | ~2 GB | ~1 GB |
| Scans per day | 75 | 25 | 25 | 25 |
| Indicator calcs per day | 75,000 | 15,000 | 15,000 | 5,000 |

---

## Testing Plan

1. **Baseline measurement:** Run current v4.3 and record time
2. **Phase 1 test:** Run with pre-compute + reduced scans
3. **Compare results:** Ensure PnL matches within 0.1%
4. **Phase 2 test:** Add Numba and parallelization
5. **Stress test:** Run full year backtest

---

## Rollback Plan

Each phase should be implemented as a separate branch:

```
main (current v4.3)
├── phase1-optimization (quick wins)
├── phase2-optimization (numba + parallel)
└── phase3-optimization (duckdb + architecture)
```

This allows easy rollback if issues arise.

---

## Dependencies to Add

```txt
numba>=0.57.0      # JIT compilation
duckdb>=0.9.0      # In-memory database
joblib>=1.3.0      # Parallel processing
```

---

## Notes

- All optimizations maintain backward compatibility
- Results should be identical to original implementation
- Monitor memory usage during optimization
- Test with small date range before full run

---

*Last Updated: January 2026*
*Version: 4.3.1 - Optimization Plan*
