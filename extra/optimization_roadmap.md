# Performance Optimization Roadmap (V4)

**Objective**: Maximize execution speed and reduce latency in the main trading loop.

---

## 1. Current Computation Profile

- **Engine**: NumPy (Vectorized C-level math for indicators).
- **Data Handling**: Pandas (Instrument master list loading and mapping).
- **Bottleneck**: Repetitive calculation of full indicator series (HMA, RSI) on every loop iteration (5s interval).

---

## 2. Short-Term Optimizations (High ROI)

### **A. Numba Integration (JIT Compilation)**

- **Target**: `analysis_v4/indicators_v4.py`
- **Action**: Decorate math-heavy functions (`calculate_hma`, `calculate_rsi`) with `@numba.jit(nopython=True)`.
- **Impact**: Translates Python math to machine code at runtime. Expected speedup: **10x - 50x**.

### **B. Direct Dictionary Caching**

- **Target**: `core_v4/data_v4.py`
- **Action**: Instead of pickling the Pandas DataFrame, pickle the finalized `token_map` and `symbol_map` dictionaries.
- **Impact**: Removes the Pandas `_build_maps` overhead during startup.

---

## 3. Long-Term Architectural Shifts

### **A. Streaming / Incremental Indicators**

- **Target**: `main_v4.py`
- **Action**: Replace full-series re-calculation with incremental updates.
- **Logic**: Use the new live tick to update the _previous_ HMA value rather than re-calculating the last 60 days of data.
- **Impact**: Reduces complexity from O(N) to O(1) per loop.

### **B. Polars Migration**

- **Target**: `core_v4/data_v4.py`
- **Action**: Replace Pandas with Polars for instrument processing.
- **Impact**: Faster multi-threaded data loading and filtering.

### **C. Async WebSocket Processing**

- **Target**: `core_v4/data_v4.py`
- **Action**: Move WebSocket tick handling to an asynchronous queue (`asyncio`).
- **Impact**: Ensures indicator calculation doesn't block the reception of live market data.

---

## 4. Hardware/Environment Tuning

- **Process Priority**: Set the Python process to "High Priority" in the OS.
- **Garbage Collection**: Manually trigger `gc.collect()` during the "Gap" session (10:05 - 10:10) to clear memory without affecting execution windows.
