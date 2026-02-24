# Issue: RVOL 5-Minute Candle Lag

## Status: Open

## Severity: Medium

## Location: `v6/main.py` -> `_scan_tradeable_stocks()`

---

## Description

RVOL is currently computed from the last completed 5-minute candle only. The current forming candle is excluded by incomplete-candle filtering, so live breakout volume is invisible until candle close.

## Current Behavior

- Scanner uses `hist_5m['volume'][-1]` from closed candle.
- Live surge in the current 5-minute bucket is ignored.

## Impact

- Breakout confirmation can be delayed by up to 5 minutes.
- Entries may be late or missed due to stale RVOL data.

## Plain-English Explanation

RVOL is meant to tell you if volume is strong right now.  
Currently it only looks at the previous closed 5-minute candle, so a live surge happening in the current candle is invisible until that candle closes.

## Proposed Fix (Detailed)

1. Track per-symbol intrabar volume snapshots in `TradingBotV6`:

```python
self.live_bar_volume_snapshot: Dict[str, int] = {}
self.live_bar_bucket_start: Optional[datetime] = None
```

2. At each new 5-minute bucket boundary:

- set `live_bar_bucket_start`,
- capture starting cumulative volume from tick field (`volume_traded`/`volume`).

3. Compute live bar volume in scanner:

```text
current_bar_vol = current_cum_vol - snapshot_cum_vol
elapsed_sec = max(1, now - bucket_start)
projected_5m_vol = current_bar_vol * (300 / elapsed_sec)
```

4. Use projected volume for RVOL while bar is forming:

- denominator remains average of prior completed 5m bars,
- fallback to old closed-candle RVOL when live volume fields are missing.

5. Add guard rails:

- clamp negative `current_bar_vol` to zero,
- if elapsed < 10s, use non-projected current bar volume to avoid noisy overshoot.

## Acceptance Criteria

- During a forming candle, RVOL changes as live volume changes.
- Projected RVOL is available before candle close for symbols with live volume data.
- If live volume field missing, old closed-candle behavior still works safely.

---

## Final Analysis (Consolidated, 2026-02-20)

This issue is valid and materially affects signal freshness.

Current behavior in `v6/main.py`:

- 5-minute history refresh is driven by elapsed monotonic interval (`INTRADAY_REFRESH_INTERVAL_SEC`) from runtime start, not candle-boundary alignment.
- Scanner RVOL uses `hist_5m['volume'][-1]` (last closed candle volume).
- Incomplete-candle filtering correctly avoids partial candles, but combined with offset refresh timing this creates avoidable lag.

Consolidated conclusion:

- Your slot-sync idea is correct and should be Phase 1.
- Live intrabar RVOL projection is still useful as Phase 2.

Recommended implementation order:

1. Align refresh trigger to next 5-minute boundary + 2 to 3 second buffer (clock-synced scheduling).
2. Refresh active-position symbols first, then candidates.
3. Add intrabar projected RVOL from cumulative tick volume with guardrails:
   - clamp negative delta to zero,
   - avoid aggressive projection in first few seconds,
   - fallback to closed-candle RVOL when live volume is unavailable.

This yields immediate improvement without destabilizing current logic.
