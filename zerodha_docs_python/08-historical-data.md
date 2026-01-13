# Kite Connect API - Historical Candle Data

## Overview

The Historical Data API provides archived OHLCV (Open, High, Low, Close, Volume) candle data for instruments across various timeframes, spanning several years.

---

## API Endpoint

| Method | Endpoint                                   | Description            |
| ------ | ------------------------------------------ | ---------------------- |
| `GET`  | `/instruments/historical/:token/:interval` | Get historical candles |

---

## URI Parameters

| Parameter   | Description                           |
| ----------- | ------------------------------------- |
| `:token`    | Instrument token from instruments API |
| `:interval` | Candle interval                       |

---

## Available Intervals

| Interval   | Description       |
| ---------- | ----------------- |
| `minute`   | 1-minute candles  |
| `3minute`  | 3-minute candles  |
| `5minute`  | 5-minute candles  |
| `10minute` | 10-minute candles |
| `15minute` | 15-minute candles |
| `30minute` | 30-minute candles |
| `60minute` | Hourly candles    |
| `day`      | Daily candles     |

---

## Query Parameters

| Parameter    | Required | Description                            |
| ------------ | -------- | -------------------------------------- |
| `from`       | Yes      | Start datetime (`yyyy-mm-dd hh:mm:ss`) |
| `to`         | Yes      | End datetime (`yyyy-mm-dd hh:mm:ss`)   |
| `continuous` | No       | `1` for continuous futures data        |
| `oi`         | No       | `1` to include Open Interest           |

---

## Basic Example

### Request

```bash
curl "https://api.kite.trade/instruments/historical/408065/5minute?from=2025-12-26+09:15:00&to=2025-12-26+10:00:00" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": {
    "candles": [
      ["2025-12-26T09:15:00+0530", 1840.0, 1845.5, 1838.25, 1843.8, 125000],
      ["2025-12-26T09:20:00+0530", 1843.85, 1848.0, 1842.5, 1847.25, 98000],
      ["2025-12-26T09:25:00+0530", 1847.3, 1850.0, 1846.0, 1849.5, 87500],
      ["2025-12-26T09:30:00+0530", 1849.55, 1852.25, 1848.75, 1851.0, 76000]
    ]
  }
}
```

---

## Candle Structure

Each candle is an array:

| Index | Field     | Description                      |
| ----- | --------- | -------------------------------- |
| 0     | timestamp | ISO 8601 timestamp with timezone |
| 1     | open      | Opening price                    |
| 2     | high      | Highest price                    |
| 3     | low       | Lowest price                     |
| 4     | close     | Closing price                    |
| 5     | volume    | Total volume                     |
| 6     | oi        | Open Interest (if `oi=1`)        |

---

## With Open Interest

For F&O instruments, include OI:

```bash
curl "https://api.kite.trade/instruments/historical/12517890/minute?from=2025-12-04+09:15:00&to=2025-12-04+09:20:00&oi=1" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": {
    "candles": [
      [
        "2025-12-04T09:15:00+0530",
        24009.9,
        24019.35,
        24001.25,
        24001.5,
        163275,
        13667775
      ],
      [
        "2025-12-04T09:16:00+0530",
        24001.0,
        24003.0,
        23998.25,
        24001.0,
        105750,
        13667775
      ],
      [
        "2025-12-04T09:17:00+0530",
        24001.0,
        24001.0,
        23995.1,
        23998.55,
        48450,
        13758000
      ]
    ]
  }
}
```

---

## Continuous Futures Data

For seamless historical data across expired contracts:

```bash
curl "https://api.kite.trade/instruments/historical/12517890/day?from=2025-01-01&to=2025-12-26&continuous=1" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### How It Works

- Pass current month's `instrument_token`
- API returns data from previous expired contracts
- Works for NFO and MCX futures
- Only available for `day` interval
- Adjusts for contract rollovers

### Use Case

Get 1 year of NIFTY futures data using current month's token:

- January 2025: Uses JAN contract data
- February 2025: Uses FEB contract data
- And so on...

---

## Granular Time Queries

Fetch specific time windows:

```bash
# Get just 15 minutes of data
curl "https://api.kite.trade/instruments/historical/408065/minute?from=2025-12-26+09:15:00&to=2025-12-26+09:30:00"
```

---

## Rate Limits

| Endpoint           | Rate Limit        |
| ------------------ | ----------------- |
| Historical candles | 3 requests/second |

---

## Python Examples

```python
from kiteconnect import KiteConnect
import datetime

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Get 5-minute candles for today
today = datetime.date.today()
data = kite.historical_data(
    instrument_token=408065,  # INFY
    from_date=datetime.datetime(today.year, today.month, today.day, 9, 15),
    to_date=datetime.datetime(today.year, today.month, today.day, 15, 30),
    interval="5minute"
)

for candle in data:
    print(f"{candle['date']}: O={candle['open']} H={candle['high']} L={candle['low']} C={candle['close']} V={candle['volume']}")

# Get daily candles for last 1 year
from_date = datetime.date.today() - datetime.timedelta(days=365)
to_date = datetime.date.today()

data = kite.historical_data(
    instrument_token=408065,
    from_date=from_date,
    to_date=to_date,
    interval="day"
)

# Get F&O data with Open Interest
data = kite.historical_data(
    instrument_token=12517890,  # NIFTY FUT
    from_date=from_date,
    to_date=to_date,
    interval="day",
    oi=True
)

for candle in data:
    print(f"{candle['date']}: Close={candle['close']} OI={candle['oi']}")

# Get continuous futures data
data = kite.historical_data(
    instrument_token=12517890,
    from_date=datetime.date(2024, 1, 1),
    to_date=datetime.date.today(),
    interval="day",
    continuous=True
)
```

---

## Response Structure (Python SDK)

The SDK returns a list of dictionaries:

```python
[
    {
        'date': datetime.datetime(2025, 12, 26, 9, 15, tzinfo=...),
        'open': 1840.0,
        'high': 1845.5,
        'low': 1838.25,
        'close': 1843.8,
        'volume': 125000,
        'oi': 13667775  # Only if oi=True
    },
    ...
]
```

---

## Building OHLC DataFrames

```python
import pandas as pd
from kiteconnect import KiteConnect
import datetime

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Fetch data
data = kite.historical_data(
    instrument_token=408065,
    from_date=datetime.date.today() - datetime.timedelta(days=30),
    to_date=datetime.date.today(),
    interval="day"
)

# Convert to DataFrame
df = pd.DataFrame(data)
df.set_index('date', inplace=True)

# Calculate indicators
df['SMA_20'] = df['close'].rolling(window=20).mean()
df['SMA_50'] = df['close'].rolling(window=50).mean()

# Calculate daily returns
df['returns'] = df['close'].pct_change()

print(df.tail())
```

---

## Data Availability

| Segment    | History Available      |
| ---------- | ---------------------- |
| NSE Equity | Several years          |
| BSE Equity | Several years          |
| NSE F&O    | Since contract listing |
| MCX        | Since contract listing |
| Currency   | Since contract listing |

---

## Common Use Cases

### 1. Intraday Backtesting

```python
# Get 1-minute data for specific date
data = kite.historical_data(
    instrument_token=408065,
    from_date=datetime.datetime(2025, 12, 20, 9, 15),
    to_date=datetime.datetime(2025, 12, 20, 15, 30),
    interval="minute"
)
```

### 2. Daily Trend Analysis

```python
# Get 200 days for moving average analysis
data = kite.historical_data(
    instrument_token=408065,
    from_date=datetime.date.today() - datetime.timedelta(days=300),
    to_date=datetime.date.today(),
    interval="day"
)
```

### 3. Volume Profile

```python
# Aggregate volume by price levels
df = pd.DataFrame(data)
df['price_bucket'] = (df['close'] // 10) * 10  # 10-point buckets
volume_profile = df.groupby('price_bucket')['volume'].sum()
```

### 4. Options OI Analysis

```python
# Get OI trends for options
data = kite.historical_data(
    instrument_token=option_token,
    from_date=datetime.date.today() - datetime.timedelta(days=30),
    to_date=datetime.date.today(),
    interval="day",
    oi=True
)
```

---

## Important Notes

1. **Rate limiting**: 3 requests/second - batch your requests
2. **Token expiry**: Expired contract tokens won't return data
3. **Data gaps**: No data for market holidays
4. **Timezone**: All timestamps are IST (UTC+5:30)
5. **Continuous data**: Only for day interval
6. **Cache data**: Store locally to avoid repeated API calls

---

## Error Handling

```python
try:
    data = kite.historical_data(
        instrument_token=408065,
        from_date=from_date,
        to_date=to_date,
        interval="5minute"
    )
except Exception as e:
    if "Rate limit" in str(e):
        time.sleep(1)
        # Retry
    else:
        raise
```

---

_Last Updated: December 2025_
