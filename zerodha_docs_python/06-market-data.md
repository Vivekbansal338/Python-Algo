# Kite Connect API - Market Data & Instruments

## Overview

The Market Data APIs provide access to instrument lists and market quotes (LTP, OHLC, depth). For real-time streaming data, see [07-websocket.md](07-websocket.md).

---

## API Endpoints

| Method | Endpoint                 | Description                           |
| ------ | ------------------------ | ------------------------------------- |
| `GET`  | `/instruments`           | Get all tradable instruments (CSV)    |
| `GET`  | `/instruments/:exchange` | Get instruments for an exchange (CSV) |
| `GET`  | `/quote`                 | Get full market quotes                |
| `GET`  | `/quote/ohlc`            | Get OHLC quotes                       |
| `GET`  | `/quote/ltp`             | Get LTP quotes                        |

---

## Part 1: Instruments

### Overview

The instruments API returns a comprehensive CSV list of all tradable instruments. This should be downloaded once daily (around 8:30 AM) and cached locally.

### Get All Instruments

```bash
curl "https://api.kite.trade/instruments" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Get Exchange-Specific Instruments

```bash
curl "https://api.kite.trade/instruments/NSE" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### CSV Response Structure

```csv
instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE
5720322,22345,NIFTY25JANFUT,,78.0,2025-01-30,,0.05,75,FUT,NFO-FUT,NFO
5720578,22346,NIFTY2512520000CE,,23.0,2025-12-25,20000,0.05,75,CE,NFO-OPT,NFO
```

### Instrument Fields

| Field              | Type   | Description                      |
| ------------------ | ------ | -------------------------------- |
| `instrument_token` | int    | Token for WebSocket subscription |
| `exchange_token`   | int    | Exchange-issued identifier       |
| `tradingsymbol`    | string | Trading symbol for orders        |
| `name`             | string | Company name (equity only)       |
| `last_price`       | float  | Last traded price                |
| `expiry`           | string | Expiry date (derivatives)        |
| `strike`           | float  | Strike price (options)           |
| `tick_size`        | float  | Minimum price movement           |
| `lot_size`         | int    | Lot size for trading             |
| `instrument_type`  | string | EQ, FUT, CE, PE                  |
| `segment`          | string | Market segment                   |
| `exchange`         | string | Exchange name                    |

### Instrument Types

| Type  | Description |
| ----- | ----------- |
| `EQ`  | Equity      |
| `FUT` | Futures     |
| `CE`  | Call Option |
| `PE`  | Put Option  |

### Segments

| Segment   | Description      |
| --------- | ---------------- |
| `NSE`     | NSE Equity       |
| `BSE`     | BSE Equity       |
| `NFO-FUT` | NSE F&O Futures  |
| `NFO-OPT` | NSE F&O Options  |
| `BFO-FUT` | BSE F&O Futures  |
| `BFO-OPT` | BSE F&O Options  |
| `CDS-FUT` | Currency Futures |
| `CDS-OPT` | Currency Options |
| `MCX`     | Commodity        |

### Best Practices

1. Download once daily (around 8:30 AM)
2. Store in database with `exchange:tradingsymbol` as unique key
3. Don't rely on `instrument_token` as permanent ID (reused after expiry)
4. Cache locally to avoid repeated API calls

---

## Part 2: Market Quotes

### Full Quote

Get complete market data including depth for up to **500 instruments**.

```bash
curl "https://api.kite.trade/quote?i=NSE:INFY&i=NSE:SBIN&i=NFO:NIFTY25JANFUT" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "NSE:INFY": {
      "instrument_token": 408065,
      "timestamp": "2025-12-26 15:45:56",
      "last_trade_time": "2025-12-26 15:45:52",
      "last_price": 1850.5,
      "last_quantity": 5,
      "buy_quantity": 25000,
      "sell_quantity": 30000,
      "volume": 7360198,
      "average_price": 1848.75,
      "oi": 0,
      "oi_day_high": 0,
      "oi_day_low": 0,
      "net_change": 15.5,
      "lower_circuit_limit": 1665.5,
      "upper_circuit_limit": 2035.5,
      "ohlc": {
        "open": 1840,
        "high": 1855,
        "low": 1835,
        "close": 1835
      },
      "depth": {
        "buy": [
          { "price": 1850.45, "quantity": 500, "orders": 5 },
          { "price": 1850.4, "quantity": 750, "orders": 8 },
          { "price": 1850.35, "quantity": 1000, "orders": 12 },
          { "price": 1850.3, "quantity": 450, "orders": 3 },
          { "price": 1850.25, "quantity": 800, "orders": 6 }
        ],
        "sell": [
          { "price": 1850.5, "quantity": 600, "orders": 4 },
          { "price": 1850.55, "quantity": 900, "orders": 7 },
          { "price": 1850.6, "quantity": 1200, "orders": 10 },
          { "price": 1850.65, "quantity": 550, "orders": 5 },
          { "price": 1850.7, "quantity": 700, "orders": 6 }
        ]
      }
    }
  }
}
```

### Quote Attributes

| Attribute             | Type   | Description                   |
| --------------------- | ------ | ----------------------------- |
| `instrument_token`    | int    | Instrument identifier         |
| `timestamp`           | string | Quote timestamp               |
| `last_trade_time`     | string | Last trade timestamp          |
| `last_price`          | float  | Last traded price             |
| `last_quantity`       | int    | Last traded quantity          |
| `buy_quantity`        | int    | Total buy orders quantity     |
| `sell_quantity`       | int    | Total sell orders quantity    |
| `volume`              | int    | Volume traded today           |
| `average_price`       | float  | Volume weighted average price |
| `oi`                  | float  | Open Interest (F&O)           |
| `oi_day_high`         | float  | OI day high                   |
| `oi_day_low`          | float  | OI day low                    |
| `net_change`          | float  | Change from previous close    |
| `lower_circuit_limit` | float  | Lower circuit price           |
| `upper_circuit_limit` | float  | Upper circuit price           |

### OHLC Sub-object

| Field   | Description        |
| ------- | ------------------ |
| `open`  | Day open price     |
| `high`  | Day high price     |
| `low`   | Day low price      |
| `close` | Previous day close |

### Market Depth

5 levels of bid/ask:

| Field      | Description               |
| ---------- | ------------------------- |
| `price`    | Price level               |
| `quantity` | Total quantity at price   |
| `orders`   | Number of orders at price |

---

### OHLC Quote

Get OHLC + LTP for up to **1000 instruments**:

```bash
curl "https://api.kite.trade/quote/ohlc?i=NSE:INFY&i=NSE:SBIN" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "NSE:INFY": {
      "instrument_token": 408065,
      "last_price": 1850.5,
      "ohlc": {
        "open": 1840,
        "high": 1855,
        "low": 1835,
        "close": 1835
      }
    }
  }
}
```

---

### LTP Quote

Get only LTP for up to **1000 instruments**:

```bash
curl "https://api.kite.trade/quote/ltp?i=NSE:INFY&i=NSE:SBIN" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "NSE:INFY": {
      "instrument_token": 408065,
      "last_price": 1850.5
    }
  }
}
```

---

## Rate Limits

| Endpoint      | Max Instruments | Rate Limit |
| ------------- | --------------- | ---------- |
| `/quote`      | 500             | 1 req/sec  |
| `/quote/ohlc` | 1000            | 1 req/sec  |
| `/quote/ltp`  | 1000            | 1 req/sec  |

---

## Instrument Format

Instruments are specified as `exchange:tradingsymbol`:

| Example                 | Description        |
| ----------------------- | ------------------ |
| `NSE:INFY`              | Infosys on NSE     |
| `BSE:RELIANCE`          | Reliance on BSE    |
| `NFO:NIFTY25JANFUT`     | Nifty Jan Futures  |
| `NFO:NIFTY2512520000CE` | Nifty Call Option  |
| `MCX:GOLDPETAL25JANFUT` | Gold Petal Futures |

---

## Python Examples

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Get all instruments
instruments = kite.instruments()  # Returns list of dicts

# Get NSE instruments only
nse_instruments = kite.instruments("NSE")

# Filter for specific stocks
nifty50_stocks = [i for i in instruments if i['segment'] == 'NSE' and i['instrument_type'] == 'EQ']

# Get full quote
quote = kite.quote("NSE:INFY", "NSE:SBIN")
print(quote["NSE:INFY"]["last_price"])
print(quote["NSE:INFY"]["ohlc"])
print(quote["NSE:INFY"]["depth"])

# Get OHLC quote
ohlc = kite.ohlc("NSE:INFY", "NSE:SBIN")
print(ohlc["NSE:INFY"]["ohlc"]["high"])

# Get LTP
ltp = kite.ltp("NSE:INFY", "NSE:SBIN")
print(ltp["NSE:INFY"]["last_price"])

# Build instrument token map for WebSocket
token_map = {}
for i in instruments:
    key = f"{i['exchange']}:{i['tradingsymbol']}"
    token_map[i['instrument_token']] = key
```

---

## Common Use Cases

### 1. Build Watchlist

```python
watchlist = ["NSE:RELIANCE", "NSE:TCS", "NSE:INFY", "NSE:HDFC", "NSE:SBIN"]
quotes = kite.quote(*watchlist)

for symbol, data in quotes.items():
    print(f"{symbol}: {data['last_price']} ({data['net_change']:+.2f})")
```

### 2. Check Market Depth

```python
quote = kite.quote("NSE:INFY")
depth = quote["NSE:INFY"]["depth"]

print("Bid Levels:")
for level in depth["buy"]:
    print(f"  {level['price']}: {level['quantity']} ({level['orders']} orders)")

print("Ask Levels:")
for level in depth["sell"]:
    print(f"  {level['price']}: {level['quantity']} ({level['orders']} orders)")
```

### 3. Find F&O Instruments

```python
nfo = kite.instruments("NFO")

# Get Nifty futures
nifty_fut = [i for i in nfo if 'NIFTY' in i['tradingsymbol'] and i['instrument_type'] == 'FUT']

# Get Nifty options expiring this month
import datetime
this_month = datetime.date.today().replace(day=1)
next_month = (this_month + datetime.timedelta(days=32)).replace(day=1)

nifty_options = [
    i for i in nfo
    if 'NIFTY' in i['tradingsymbol']
    and i['instrument_type'] in ['CE', 'PE']
    and i['expiry'] and this_month <= datetime.datetime.strptime(i['expiry'], '%Y-%m-%d').date() < next_month
]
```

---

## Important Notes

1. **Check key existence**: If no data for an instrument, key will be absent
2. **Indices**: Use `INDICES` exchange (e.g., `INDICES:NIFTY 50`)
3. **Spaces in symbols**: URL encode spaces (e.g., `NIFTY%2050`)
4. **Cache instruments**: Download once daily to avoid rate limits
5. **Use WebSocket**: For real-time data, not polling quotes

---

_Last Updated: December 2025_
