# Comment on V5 Strategy & Assessment (GPT-5.2-Codex)

## Overall take

Both documents are thoughtful and mostly aligned with the codebase. The strategy document is a strong operational spec; the assessment document is directionally correct and highlights real engineering and risk gaps. A few mismatches and clarifications would improve accuracy and reduce ambiguity.

---

## What matches the code well

- **Playbooks & timing**: matches `main_v5.py` playbook windows and cutoffs.
- **Prev-close anchor**: implemented across sector/stock percent change and RS calculations.
- **Sector scoring**: weighted composite score and absolute-magnitude ranking are aligned.
- **Stock grading**: A+/A/B/C scoring, RVOL thresholds, StochRSI logic, and sector rank scoring are correct.
- **Gate checks**: spread/ATR, circuit buffer, and basic data validity match `ExecutionFilters.check_gate`.
- **Stops/targets/partial exit**: aligns with `lifecycle_v5.py` (1.5R partial, breakeven move, chandelier trailing).
- **5‑minute refresh**: intraday refresh logic is implemented to prevent RVOL/HMA staleness.

---

## Mismatches or missing nuances

### 1) HMA “Immediate disqualifier”

- **Doc says**: HMA MIXED is immediate Grade C.
- **Code does**: MIXED HMA still gets **1 point** (not auto‑C). Auto‑C is only enforced for RVOL below threshold or StochRSI divergence. Direction “NONE” doesn’t force an early reject either.

### 2) ADV reference line

- **Doc says**: `execution_v5/strategy_v5.py:663`.
- **Actual**: ADV filtering is in `main_v5.py` using `ExecutionFilters.calculate_adv_crores`, and the threshold is in `core_v5/config_v5.py`.

### 3) Regime naming vs multipliers

- **Doc uses**: ELEVATED regime.
- **Code uses**: TRENDING/NEUTRAL/MEAN_REVERT/EXTREME only. The multiplier `VIX_MULT_ELEVATED` exists, but regime label “ELEVATED” isn’t used in `MarketRegimeDetector.get_regime`.

### 4) Risk “Layer 5” – daily drawdown tracking

- **Doc says**: daily drawdown tracking with persistence.
- **Code does**: stores `daily_high_equity` in state, but **risk logic doesn’t use it**; only `daily_start_equity` is used for drawdown checks. No intraday high‑watermark enforcement exists.

---

## Assessment doc: mostly agree (with a few clarifications)

### Agree ✅

- Complexity is high; signal stack is heavy and brittle.
- Indicator lag is real for HMA + StochRSI windows.
- VWAP breadth can lag trends.
- WebSocket dependency and lack of fallback is a risk.
- No tick staleness checks, no test coverage, and missing holiday handling are real gaps.

### Clarify ⚠️

- “11 scoring components” is imprecise. The sector model uses **5** components; stock grading uses **5**; gate is binary. Complexity concern is valid, but component count should be corrected.
- “Daily drawdown tracking with persistence” is only partially true; the persisted high‑water mark is not used in risk logic.

---

## Suggestions (actionable, minimal scope)

1. **Tick staleness filter**: reject/ignore ticks older than 30–60s before signal/risk logic.
2. **Intraday high‑water mark**: use `daily_high_equity` to prevent repeated drawdown breaches.
3. **WebSocket watchdog**: fallback to REST polling if tick stream is stale/disconnected.
4. **Correlation/sector concentration**: implement correlation guard or stricter per‑sector cap.
5. **Normalize composite scores**: optional, but would simplify thresholds and interpretability.
6. **Unit tests**: start with `indicators_v5.py` and `strategy_v5.py` (RS, ATR, StochRSI, HMA).

---

## Bottom line

- **Strategy doc**: high fidelity but a few wording/logic mismatches (HMA auto‑C, regime label, ADV reference).
- **Assessment doc**: solid critique; most points stand, with minor precision fixes.

If you want, I can patch the two MD files to align wording with the actual implementation.
