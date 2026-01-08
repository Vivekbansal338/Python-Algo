# Zerodha/Kite API usage review (07.python_practice v3)

Date: 2026-01-06

This note reviews all **v3** code under `07.python_practice/` with a narrow goal:

1. **List every Zerodha (Kite) API call** being made (REST + WebSocket + login/token endpoints).
2. Explain **when/how often** those calls happen in each run mode.
3. Recommend **what data can be stored locally** (files/DB) so the system can reuse it and reduce API usage + speed up analysis.

---

## Files scanned (v3)

- `DataManager_v3.py` — main KiteConnect wrapper (REST + WebSocket) and in-memory caching.
- `sector_dashboard_v3.py` — orchestration: universe load → snapshot → periodic updates → sector ranking → stock analysis.
- `sector_dashboard_rich_v3.py` — UI runner; calls dashboard methods and controls when stock historical data is loaded.
- `stock_analyzers.py` — indicators (no Zerodha calls).
- `opening_range_tracker.py` — OR logic (no Zerodha calls).
- `generate_token.py` — token generation via Zerodha HTTP endpoints (requests), writes to `.env`.

---

## 1) Inventory: Zerodha endpoints used

### A) KiteConnect (kiteconnect SDK)

All calls below come from `DataManager_v3.py`.

| API / method                                                          | Underlying endpoint (conceptual)                 | Where                                                       | Purpose                                                    | Notes                                                            |
| --------------------------------------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------- |
| `KiteConnect(api_key=...)` + `set_access_token()`                     | auth setup                                       | `DataManagerV3.connect()`                                   | initialize session                                         | not a network call by itself (setup)                             |
| `kite.profile()`                                                      | `GET /user/profile`                              | `DataManagerV3.connect()`                                   | verify token + fetch user profile                          | done once per process start                                      |
| `kite.instruments(exchange)`                                          | `GET /instruments/{exchange}`                    | `DataManagerV3.load_instruments()`                          | download instrument master (token mapping etc.)            | currently cached in-memory for 12h; **not persisted**            |
| `kite.quote(["NSE:..."])`                                             | `GET /quote`                                     | `DataManagerV3.get_quotes()` and `update_snapshot_quotes()` | fetch full quote incl. OHLC, volume, VWAP, depth, circuits | can be heavy payload; currently used broadly                     |
| `kite.historical_data(token, from_date, to_date, interval)`           | `GET /instruments/historical/{token}/{interval}` | `DataManagerV3.get_historical_data()`                       | OHLCV history for RS + indicators                          | cached in-memory for 15 min; key uses date ranges                |
| `KiteTicker(api_key, access_token)` + `ticker.connect(threaded=True)` | WebSocket (`wss://...`)                          | `DataManagerV3.start_websocket()`                           | stream tick data                                           | `mode="quote"` by default; subscribes to **all snapshot tokens** |
| `ws.subscribe(tokens)` + `ws.set_mode(...)`                           | WS subscription control                          | `start_websocket.on_connect()`                              | choose tick payload size                                   | modes: `MODE_LTP`, `MODE_QUOTE`, `MODE_FULL`                     |

### B) Direct Zerodha HTTP endpoints (requests)

All calls below come from `generate_token.py`.

| Endpoint                                     |   Method | Where                             | Purpose                                   |
| -------------------------------------------- | -------: | --------------------------------- | ----------------------------------------- |
| `https://kite.zerodha.com/connect/login?...` |  browser | `TokenGenerator.get_login_url()`  | interactive login to get `request_token`  |
| `https://api.kite.trade/session/token`       |   `POST` | `TokenGenerator.exchange_token()` | exchange `request_token` → `access_token` |
| `https://api.kite.trade/session/token`       | `DELETE` | `TokenGenerator.logout()`         | invalidate token                          |
| `https://api.kite.trade/user/profile`        |    `GET` | `TokenGenerator.validate_token()` | validate access token                     |

---

## 2) When do these calls happen? (per run mode)

### Initialization (common)

Triggered by `SectorDashboardV3.initialize()`:

1. Universe load from `../config/universe.json` via `UniverseLoader` (local file).
2. `DataManagerV3.connect()` → **1 call**: `kite.profile()`.
3. `DataManagerV3.load_instruments("NSE")` → **1 call**: `kite.instruments("NSE")` (unless in-memory cache is warm).
4. Snapshot created: includes VIX + NIFTY + 16 sector indices + all configured stocks.

### Polling mode (`sector_dashboard_v3.py` main loop or `sector_dashboard_rich_v3.py --live --interval`)

Each `dashboard.update()` currently does:

1. `update_snapshot_quotes(snapshot)` → **1 call** `kite.quote([...])` for **ALL instruments in snapshot**.
2. `update_snapshot_historical(snapshot, 20)` → up to **~18 calls** `kite.historical_data(...)` (VIX + NIFTY + 16 sectors). In practice this is often served from the **15-min in-memory cache**, but after restart it’s full calls.
3. If selected sectors exist and stock history not loaded yet:
   - `update_stock_historical_daily(..., days=50)` → **1 historical call per stock** in selected sectors.
   - `update_stock_historical_5m(... today ...)` → **1 historical call per stock** in selected sectors.

Important: the “stock history load” step is the **largest call spike** in v3.

### WebSocket live mode (`sector_dashboard_rich_v3.py --live --websocket`)

- Starts WebSocket and subscribes to **all snapshot tokens**.
- Still makes REST calls:
  - On startup UI: `update_snapshot_historical(..., 20)` (same as above)
  - After initial WS calc: `update_snapshot_quotes(snapshot)` is called once to populate bid/ask/depth/circuit values.
  - When sectors change, it loads stock historical (daily + 5m) for new sectors.

---

## 3) Current caching behavior (what exists today)

Implemented in `DataManager_v3.py`:

- Instruments cache: `self._instruments_cache` (TTL: **12h**) ✅ but **memory-only**.
- Historical cache: `self._historical_cache` (TTL: **15 min**) ✅ but **memory-only**.
- Quote cache: constants exist (`QUOTE_CACHE_SECONDS = 1`) but there is **no implemented quote cache** (quotes are fetched whenever `update_snapshot_quotes()` is called).

Implication:

- Within a single run, repeated historical calls are reduced.
- Across restarts, **everything is fetched again**.

---

## 4) Biggest API-cost drivers in v3

### Driver #1: Quoting the entire universe every update

`update_snapshot_quotes()` builds symbols for **all instruments** in the snapshot:

- VIX + NIFTY + 16 sectors + (potentially) 200–300 stocks.

In polling mode, this can be **one large `quote()` call per interval**. The default interval in `sector_dashboard_v3.py` is 900s (good), but `sector_dashboard_rich_v3.py` polling default is 60s (aggressive for full-universe quotes).

### Driver #2: Stock historical loading (daily + 5m) for every stock in selected sectors

When selected sectors are computed, v3 fetches:

- **50+ days daily OHLCV** for each stock (1 call per stock)
- **today’s 5-minute OHLCV** for each stock (1 call per stock)

If 3–5 sectors contain ~40–100 stocks, that’s easily **80–200 historical API calls** as a burst.

### Driver #3: Historical for sectors called on every polling update

Even though cached for 15 minutes, `update_snapshot_historical()` is invoked every cycle in polling mode.

---

## 5) What data should be stored locally to reduce API calls?

### A) Instrument master (tokens / metadata)

**What to store:**

- Full NSE instruments dump (or at minimum mapping for symbols used).

**Why:**

- `kite.instruments()` is large and slow; tokens rarely change intraday.

**Recommended storage:**

- Simple: `cache/instruments_NSE.csv` + `cache/instruments_meta.json`
- Better: SQLite table `instruments` (recommended; built-in `sqlite3` requires no extra dependency)

**Refresh rule:**

- Once per day pre-market, or every 12h.

### B) Daily OHLCV history (stocks + indices + VIX + sectors)

**What to store:**

- Daily candles for each instrument token (at least last 80–120 trading days).

**Why:**

- Your indicators (HMA(16/40), ATR(10), StochRSI) only need daily history.
- Daily candles update slowly; fetching 50 days repeatedly is waste.

**Refresh rule:**

- Only update once after market close, or fetch last 2–3 days each morning (to handle holidays / missing).

### C) Intraday 5-minute candles (only for today, only for a subset)

**What to store:**

- Today’s 5-min candles per token.

**Why:**

- HMA(20) on 5-min is your “intraday layer”.
- Fetching the entire day for many symbols is expensive.

**Refresh rule options:**

1. **Best (no REST): build candles from WebSocket ticks**

   - Subscribe selected stocks in WS mode that includes enough fields.
   - Maintain an in-memory + disk “candle builder” that aggregates ticks into 5-min OHLCV.
   - Persist only today’s partial candles.

2. **If you keep REST historical:**
   - Fetch only once per day for a symbol, then refresh incrementally by re-fetching the last ~30 minutes (small overlap) every 5–10 minutes.

### D) Volume profile for time-adjusted RVOL (future-proof)

`stock_analyzers.py` already has a placeholder for “time-adjusted RVOL” (preferred per your concepts).

**What to store:**

- A per-symbol intraday expected volume curve (e.g., average cumulative volume at each hour / 5-min bucket).

**Why:**

- Eliminates guesswork and avoids needing constant “full day” 5-min pulls.

---

## 6) Concrete optimizations to reduce Zerodha calls (prioritized)

### Quick wins (minimal code changes)

1. **Stop quoting all stocks when you only need sector ranks**

   - For sector ranking you need VIX + NIFTY + sector index prices.
   - Fetch quotes only for:
     - VIX token
     - NIFTY token
     - 16 sector tokens
   - Then, once sectors are selected, quote only stocks in selected sectors.

2. **Use `ltp()` for bulk, `quote()` only for the short-list**

   - `quote()` is heavy (depth, OHLC, etc.).
   - Use `ltp()` for broad universe price refreshes.
   - Use `quote()` only for:
     - stocks that you’re evaluating for gate/grade (needs depth/circuit/VWAP)
     - or a top-N candidate list.

3. **Throttle `update_snapshot_historical()`**

   - In polling mode, don’t call it every cycle.
   - Call it:
     - once at startup
     - then every 30–60 minutes, or only if `is_historical_stale` for VIX/sectors.

4. **Load stock historical only for likely candidates**
   - First pass: select sectors.
   - Second pass: compute a candidate list of stocks (e.g., top by liquidity/ADV + above VWAP + price change filter).
   - Only then fetch daily/5m history for those candidates.

### Medium wins (persisted caching)

5. **Persist caches across runs** (biggest practical speed-up)

Recommended: **SQLite** (works on Windows out of the box).

- `cache/marketdata.sqlite`
  - `instruments(exchange, tradingsymbol, instrument_token, ... , updated_at)`
  - `ohlcv(token, interval, ts, open, high, low, close, volume, vwap, PRIMARY KEY(token, interval, ts))`
  - `meta(key, value)` for last refresh timestamps

Then:

- `get_historical_data()` first tries DB; only hits API for missing ranges.

6. **Persist “computed features” too** (optional)

You can store results like:

- ATR10, HMA40/16, StochRSI K/D, ADV, computed on daily close

This makes startup and ranking even faster (compute once per day), leaving intraday work mostly to live prices.

### Advanced (highest payoff, more engineering)

7. **Hybrid WS + REST design**

- WS for live LTP/quote for the small set you care about.
- REST only for:
  - daily candles (once/day)
  - instrument master (once/day)

8. **Add API-call accounting + backoff**

You already have `prometheus_client` in requirements.

- Count calls by endpoint type (quote/historical/instruments/ws reconnects).
- Track request latency.
- Add exponential backoff and “cooldown mode” when rate-limit errors occur.

---

## 7) Notes specific to this codebase

- `DataManagerV3` already has the right architectural idea: one wrapper, rate-limits, caching. The missing piece is **persistence**.
- There is a `redis` dependency in `requirements.txt` but it’s not used in v3. Redis can help for cross-process caching, but for your single-machine workflow, **SQLite on disk** is simpler and more reliable.
- The highest-ROI change is to **separate “sector ranking refresh” from “stock deep analysis refresh”** and only fetch deep data for the short-list.

---

## 8) Suggested next implementation steps (if you want me to code it)

1. Add a `cache/` folder under `07.python_practice/`.
2. Implement `MarketDataStore` (SQLite) with:
   - `get_instruments(exchange)`
   - `get_ohlcv(token, interval, from_ts, to_ts)`
   - `upsert_ohlcv(rows)`
3. Modify `DataManagerV3.load_instruments()` to:
   - load from DB if fresh; else call API and persist.
4. Modify `DataManagerV3.get_historical_data()` to:
   - load missing ranges from DB; only call API for gaps; persist results.
5. Modify the dashboard flow to:
   - quote only indices/sectors initially
   - quote only selected-sector stocks for gate/grade

If you want, tell me which storage you prefer (**SQLite** vs **Parquet** vs **Redis**) and whether you want caching to be **per-day** or **rolling-window**, and I’ll implement it cleanly.
