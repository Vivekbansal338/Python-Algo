# Sector Score Weight Optimization — V6.2 Industry-Standard Playbook (Zero-Inclusive)

**Last updated:** 2026-02-24  
**Scope:** This document is explicitly for **V6.2** optimization (interpreting your “v2” request as `v6.2`).  
**Baseline (from attached V6.2 analysis):**

- Net PnL: **₹153,157.31**
- Return: **15.32%**
- Max Drawdown: **9.12%**
- Profit Factor: **1.09**
- Win Rate: **63.44%**
- Avg Trade PnL (Expectancy proxy): **₹64.43**
- Avg Daily PnL: **₹754.47**
- Trades: **2,377**

---

## 1) What We Are Optimizing in V6.2

V6.2 uses `brain.py` sector scoring + V6.2 risk/execution rules. We optimize only the sector-composite parameters:

```
composite = structural_rs * W_structural
               + shortterm_rs  * W_shortterm
               + intraday_rs   * W_intraday
               + breadth       * W_breadth
               + nifty_pct     * W_nifty
```

Bias gate:

```
if composite >= +T: LONG
if composite <= -T: SHORT
else:               NEUTRAL
```

### Mandatory constraint

All weights must include 0 in search space (feature can be turned off).

---

## 2) V6.2-Specific Goals

For this V6.2 optimization, the objective is to build the **best overall trading system** using robust metrics from the analysis JSON. The optimization must aim to:

1. Improve risk-adjusted return (not only raw PnL)
2. Improve robustness and consistency across walk-forward folds
3. Maintain healthy trade count (avoid fragile low-N solutions)
4. Improve system quality metrics together: return, PF, expectancy, DD, and stability

---

## 3) Industry-Standard Optimization Stack (Recommended)

### A) Coarse exploration (Sobol/LHS)

Run **150–250** space-filling trials to map global behavior.

### B) Bayesian optimization (Optuna TPE)

Run **400–800** trials (single-objective or multi-objective) seeded from coarse exploration.

### C) Multi-objective refinement (NSGA-II)

Generate Pareto-optimal candidates balancing:

- maximize out-of-sample return
- minimize max drawdown
- maximize profit factor and expectancy

### D) Nested walk-forward validation (required)

- Inner loop: tune on train
- Outer loop: evaluate locked parameters on unseen test

This is the practical institutional standard for strategy parameter tuning.

---

## 4) Search Space for V6.2 (Zero Included)

### Continuous search (main run)

- `W_structural`: 0 to 150
- `W_shortterm`: 0 to 150
- `W_intraday`: 0 to 200
- `W_breadth`: 0 to 150
- `W_nifty`: 0 to 250
- `T`: 0 to 35

### Discrete sanity grid (quick pass)

- Each weight: `{0, 5, 10, 20, 40, 80, 120, 160}`
- `W_nifty`: `{0, 10, 30, 60, 120, 180, 240}`
- `T`: `{0, 5, 10, 15, 20, 25, 30, 35}`

Why this works:

- tests full model and sparse model families
- allows optimizer to discover that some factors may be unnecessary
- includes low-threshold and high-threshold regimes

---

## 5) Objective Function (V6.2 Practical)

Do not optimize raw PnL only.

Use a composite objective focused on total system quality:

```
score =
  + 0.30 * norm(Return)
  + 0.20 * norm(Sortino)
  + 0.15 * norm(ProfitFactor, capped)
  + 0.15 * norm(Expectancy)
  + 0.05 * norm(WinRate)
  - 0.15 * norm(MaxDrawdown)
  - penalties
```

Where:

- penalties include:
  - too few trades (`trades < N_min`)
  - unstable fold performance (high variance across out-of-sample windows)
  - severe concentration risk (single time bucket/regime dominates)

---

## 6) Data Split and Validation Protocol

Use rolling walk-forward (no random shuffling):

```
Window 1: Train [M1..M4], Test [M5]
Window 2: Train [M2..M5], Test [M6]
Window 3: Train [M3..M6], Test [M7]
...
```

Minimums:

- at least 5 out-of-sample folds
- fixed slippage/cost assumptions across all runs
- fixed risk rules and position sizing rules (only weights + threshold change)

---

## 7) Selection Rule (What to Deploy for V6.2)

Select candidate only if it beats V6.2 baseline **out-of-sample** on majority of folds.

### Baseline hurdle values

- Return > **15.32%**
- Max Drawdown < **9.12%**
- Profit Factor > **1.09**
- Win Rate ≥ **63.44%** (or better expectancy if win-rate is slightly lower)
- Expectancy > **₹64.43**

### Deployment criteria

1. Out-of-sample return improvement
2. Drawdown not worse than baseline
3. Profit factor improvement
4. Expectancy improvement with stable trade count
5. Stable across folds (no single-window dependence)

If two candidates are close, choose simpler one (more near-zero weights).

---

## 8) Statistical Checks Before Final Lock

Run these before production decision:

- bootstrap confidence intervals for return and max DD
- paired fold-wise comparison vs baseline
- overfit gap check (train metric − test metric)

Reject any candidate with large overfit gap even if in-sample PnL is high.

---

## 9) Implementation Contract (V6.2-Compatible)

Parameterize V6.2 engine (new variant, e.g., `sector_engine_v6.2_opt.py`) with:

```python
sector_weights: Optional[Dict[str, float]] = None
bias_threshold: Optional[float] = None
```

Rules:

- if params are `None`, preserve current V6.2 behavior exactly
- if provided, compute composite score locally in engine and set sector bias using `T`
- keep all other V6.2 logic unchanged (risk, stops, capital exposure, execution gates)

---

## 10) Recommended Execution Plan

### Phase 0 (0.5–1 day)

- parameterize V6.2 weights/threshold
- add deterministic seed + trial logging

### Phase 1 (same day)

- 200 Sobol/LHS trials
- identify dead factors (weights repeatedly near 0)

### Phase 2 (1–2 days)

- 600 Optuna TPE trials
- prune weak trials early

### Phase 3 (1–2 days)

- nested walk-forward on top 20 candidates
- pick robust winner and backup

### Phase 4 (same day)

- freeze winner config for one review cycle
- monitor live drift and retrain schedule

---

## 11) Final Recommendation for V6.2

Best path to real, useful outcomes:

1. zero-inclusive search (all weights can be 0)
2. Optuna TPE + NSGA-II optimization
3. nested walk-forward validation
4. deploy only if out-of-sample metrics beat V6.2 baseline consistently

This gives the highest chance of robust improvement without curve-fitting.
