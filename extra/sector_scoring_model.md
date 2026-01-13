# V4.1 Sector Scoring Model (Weighted Z-Score)

**Objective**: Absolute Momentum Ranking with Broad Market "Gravity".

## The Formula
> **`Score = (3 * Struct_RS) + (10 * Short_RS) + (20 * Intra_RS) + (40 * Net_Breadth) + (30 * Nifty_Intra)`**

## The "Relative Strength Trap" (Why Nifty Vector?)
**The Problem**: In a crashing market (Nifty -3%), a sector falling -1% shows Positive Relative Strength (+2%). This creates a false "LONG" bias, leading the bot to buy falling stocks.

**The Solution**: The **Nifty Vector** acts as a gravity force.
*   **Bear Market**: Nifty (-3%) * Weight (30) = **-90 points**. This massive penalty crushes the +20 points from Relative Strength, flipping the final score to **SHORT**.
*   **Result**: The system correctly identifies that "Falling Less" is still "Falling," preventing dangerous counter-trend buys.

## Component Analysis & Weight Logic

| Component | Formula | Typical Range | Norm Weight | Impact Points | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Struct RS** | `Sec20d - Nif20d` | -5% to +5% | **3.0** | +/- 15 pts | **Advisor**: Historical context. Low weight to prevent legacy bias. |
| **Short RS** | `Sec3d - Nif3d` | -3% to +3% | **10.0** | +/- 30 pts | **Tactician**: Recent swing strength. |
| **Intra RS** | `SecDay - NifDay` | -1.5% to +1.5% | **20.0** | +/- 30 pts | **Prince**: Immediate relative flow. |
| **Net Breadth** | `Bull% - Bear%` | -1.0 to +1.0 | **40.0** | +/- 40 pts | **King**: Internal reality check. Highest authority. |
| **Nifty Vector**| `Nifty %` | -1.0% to +1.0% | **30.0** | +/- 30 pts | **Gravity**: The Tide. Prevents "False Longs" in Bear markets. |

## Research Instructions (Future Optimization)
The "Typical Range" and "Weights" above are currently heuristic (based on standard market behavior). To optimize this model scientifically:

1.  **Data Collection**: Log `Struct_RS`, `Intra_RS`, `Breadth`, and `Nifty_Pct` values daily for 3 months.
2.  **Normalization**: Calculate the **Standard Deviation (Sigma)** for each component.
3.  **Optimization**: Adjust the weights so that `Weight * 1 Sigma` produces roughly equal impact points (e.g., 25 pts) across all components.
    *   *Hypothesis*: Nifty moves might be smaller (lower sigma) than Sector RS, justifying an even higher weight (e.g., 40) to equalize impact.
4.  **Backtest**: Run the scoring engine on historical data to see if it correctly identifies the top performing sectors of the next day.

**Update Frequency**: Review these weights quarterly.
