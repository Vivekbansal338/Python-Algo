# Kite Connect API - WebSocket Streaming

## Overview

The WebSocket API provides real-time streaming market data with low latency. It's the most efficient way to receive live quotes during market hours.

---

## Key Features

- **Up to 3000 instruments** per connection
- **Up to 3 WebSocket connections** per API key
- **Three modes**: LTP (8 bytes), Quote (44 bytes), Full (184 bytes)
- **Binary protocol** for market data (efficient)
- **Text messages** for order postbacks and alerts

---

## Connection

### Endpoint

```
wss://ws.kite.trade?api_key=YOUR_API_KEY&access_token=YOUR_ACCESS_TOKEN
```

### JavaScript Example

```javascript
var ws = new WebSocket("wss://ws.kite.trade?api_key=xxx&access_token=yyy");

ws.onopen = function () {
  console.log("Connected");
  // Subscribe to instruments
  ws.send(
    JSON.stringify({
      a: "subscribe",
      v: [408065, 779521], // INFY, SBIN
    })
  );
};

ws.onmessage = function (event) {
  if (event.data instanceof Blob) {
    // Binary market data - parse it
  } else {
    // Text message (postbacks, errors)
    console.log(JSON.parse(event.data));
  }
};
```

---

## Request Structure

Requests are JSON messages with `a` (action) and `v` (value):

```javascript
{
    "a": "action_name",
    "v": value
}
```

### Available Actions

| Action        | Value                  | Description                  |
| ------------- | ---------------------- | ---------------------------- |
| `subscribe`   | `[token, ...]`         | Subscribe to instruments     |
| `unsubscribe` | `[token, ...]`         | Unsubscribe from instruments |
| `mode`        | `[mode, [token, ...]]` | Set streaming mode           |

### Examples

```javascript
// Subscribe to INFY and SBIN
ws.send(
  JSON.stringify({
    a: "subscribe",
    v: [408065, 779521],
  })
);

// Set INFY to full mode (with depth)
ws.send(
  JSON.stringify({
    a: "mode",
    v: ["full", [408065]],
  })
);

// Set SBIN to LTP only mode
ws.send(
  JSON.stringify({
    a: "mode",
    v: ["ltp", [779521]],
  })
);

// Unsubscribe from SBIN
ws.send(
  JSON.stringify({
    a: "unsubscribe",
    v: [779521],
  })
);
```

---

## Streaming Modes

| Mode    | Size      | Data Included                         |
| ------- | --------- | ------------------------------------- |
| `ltp`   | 8 bytes   | Token + LTP only                      |
| `quote` | 44 bytes  | Token + OHLC + Volume + OI (no depth) |
| `full`  | 184 bytes | Complete data including market depth  |

---

## Binary Message Structure

Market data is sent as binary. Each message contains one or more packets:

```
┌────────────────────────────────────────────────────────┐
│ Bytes [0-2]: Number of packets (int16)                 │
├────────────────────────────────────────────────────────┤
│ Bytes [2-4]: Length of packet 1 (int16)                │
│ Bytes [4 - 4+L1]: Packet 1 data                        │
├────────────────────────────────────────────────────────┤
│ Bytes [4+L1 - 4+L1+2]: Length of packet 2 (int16)      │
│ Bytes [4+L1+2 - ...]: Packet 2 data                    │
├────────────────────────────────────────────────────────┤
│ ... more packets ...                                   │
└────────────────────────────────────────────────────────┘
```

---

## Quote Packet Structure

### Full Mode (184 bytes)

| Bytes  | Type  | Field                                |
| ------ | ----- | ------------------------------------ |
| 0-4    | int32 | instrument_token                     |
| 4-8    | int32 | last_price (÷100 for price)          |
| 8-12   | int32 | last_quantity                        |
| 12-16  | int32 | average_price                        |
| 16-20  | int32 | volume                               |
| 20-24  | int32 | buy_quantity                         |
| 24-28  | int32 | sell_quantity                        |
| 28-32  | int32 | open                                 |
| 32-36  | int32 | high                                 |
| 36-40  | int32 | low                                  |
| 40-44  | int32 | close                                |
| 44-48  | int32 | last_trade_time (Unix timestamp)     |
| 48-52  | int32 | open_interest                        |
| 52-56  | int32 | oi_day_high                          |
| 56-60  | int32 | oi_day_low                           |
| 60-64  | int32 | exchange_timestamp                   |
| 64-184 | bytes | Market depth (10 entries × 12 bytes) |

### Quote Mode (44 bytes)

Bytes 0-44 from above (ends at close price).

### LTP Mode (8 bytes)

| Bytes | Type  | Field            |
| ----- | ----- | ---------------- |
| 0-4   | int32 | instrument_token |
| 4-8   | int32 | last_price       |

---

## Index Packet Structure

Indices have a different, simpler structure:

| Bytes | Type  | Field                               |
| ----- | ----- | ----------------------------------- |
| 0-4   | int32 | token                               |
| 4-8   | int32 | last_price                          |
| 8-12  | int32 | high                                |
| 12-16 | int32 | low                                 |
| 16-20 | int32 | open                                |
| 20-24 | int32 | close                               |
| 24-28 | int32 | price_change                        |
| 28-32 | int32 | exchange_timestamp (full mode only) |

---

## Market Depth Structure

Each depth entry is 12 bytes (10 entries total = 120 bytes):

| Bytes | Type    | Field    |
| ----- | ------- | -------- |
| 0-4   | int32   | quantity |
| 4-8   | int32   | price    |
| 8-10  | int16   | orders   |
| 10-12 | padding | (skip)   |

- Entries 1-5: Bid (buy) levels
- Entries 6-10: Ask (sell) levels

---

## Price Conversion

All prices are in paise (integer):

```python
# For equities and most instruments
actual_price = received_price / 100

# For currencies (CDS)
actual_price = received_price / 10000000
```

---

## Text Messages (Postbacks)

Non-binary messages are JSON text:

```json
{
    "type": "order",
    "data": {
        "order_id": "123456",
        "status": "COMPLETE",
        ...
    }
}
```

### Message Types

| Type      | Description            |
| --------- | ---------------------- |
| `order`   | Order update postback  |
| `error`   | Error message          |
| `message` | Broker alerts/messages |

---

## Heartbeat

If no data to stream, API sends 1-byte heartbeat every few seconds to keep connection alive. This can be safely ignored.

---

## Auto Reconnection

The Python library handles reconnection automatically:

| Parameter             | Default | Description                          |
| --------------------- | ------- | ------------------------------------ |
| `reconnect`           | True    | Enable auto-reconnect                |
| `reconnect_max_tries` | 50      | Max reconnection attempts            |
| `reconnect_max_delay` | 60      | Max delay between attempts (seconds) |
| `connect_timeout`     | 30      | Connection timeout (seconds)         |

Reconnection uses exponential backoff starting from 2 seconds.

---

## Python SDK Example

```python
import logging
from kiteconnect import KiteTicker

logging.basicConfig(level=logging.DEBUG)

# Initialize
kws = KiteTicker("your_api_key", "your_access_token")

def on_ticks(ws, ticks):
    """Received tick data"""
    for tick in ticks:
        print(f"Token: {tick['instrument_token']}")
        print(f"LTP: {tick['last_price']}")
        if 'ohlc' in tick:
            print(f"OHLC: {tick['ohlc']}")
        if 'depth' in tick:
            print(f"Best Bid: {tick['depth']['buy'][0]}")
            print(f"Best Ask: {tick['depth']['sell'][0]}")

def on_connect(ws, response):
    """Connected - subscribe to instruments"""
    # Subscribe to INFY and SBIN
    ws.subscribe([408065, 779521])

    # Set INFY to full mode
    ws.set_mode(ws.MODE_FULL, [408065])

    # Set SBIN to quote mode
    ws.set_mode(ws.MODE_QUOTE, [779521])

def on_close(ws, code, reason):
    """Connection closed"""
    print(f"Closed: {code} - {reason}")
    ws.stop()

def on_error(ws, code, reason):
    """Error occurred"""
    print(f"Error: {code} - {reason}")

def on_reconnect(ws, attempts):
    """Reconnecting"""
    print(f"Reconnecting... attempt {attempts}")

def on_noreconnect(ws):
    """Max reconnection attempts reached"""
    print("Max reconnection attempts reached")

def on_order_update(ws, data):
    """Order update received"""
    print(f"Order update: {data}")

# Assign callbacks
kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error
kws.on_reconnect = on_reconnect
kws.on_noreconnect = on_noreconnect
kws.on_order_update = on_order_update

# Start (blocking call)
kws.connect()
```

---

## Tick Structure (Python)

```python
{
    'instrument_token': 408065,
    'mode': 'full',
    'tradable': True,
    'last_price': 1850.5,
    'last_quantity': 10,
    'average_price': 1848.75,
    'volume': 7360198,
    'buy_quantity': 25000,
    'sell_quantity': 30000,
    'change': 0.84,  # Percentage change
    'last_trade_time': datetime.datetime(2025, 12, 26, 15, 29, 58),
    'timestamp': datetime.datetime(2025, 12, 26, 15, 30, 0),
    'oi': 0,
    'oi_day_high': 0,
    'oi_day_low': 0,
    'ohlc': {
        'open': 1840,
        'high': 1855,
        'low': 1835,
        'close': 1835
    },
    'depth': {
        'buy': [
            {'price': 1850.45, 'quantity': 500, 'orders': 5},
            {'price': 1850.40, 'quantity': 750, 'orders': 8},
            # ... 3 more levels
        ],
        'sell': [
            {'price': 1850.50, 'quantity': 600, 'orders': 4},
            {'price': 1850.55, 'quantity': 900, 'orders': 7},
            # ... 3 more levels
        ]
    }
}
```

---

## Methods

| Method                     | Description                  |
| -------------------------- | ---------------------------- |
| `connect(threaded=False)`  | Start WebSocket connection   |
| `close()`                  | Close connection             |
| `stop()`                   | Stop event loop              |
| `is_connected()`           | Check connection status      |
| `subscribe([tokens])`      | Subscribe to instruments     |
| `unsubscribe([tokens])`    | Unsubscribe from instruments |
| `set_mode(mode, [tokens])` | Set streaming mode           |
| `resubscribe()`            | Resubscribe to all tokens    |
| `stop_retry()`             | Stop reconnection attempts   |

---

## Mode Constants

```python
kws.MODE_LTP    # LTP only
kws.MODE_QUOTE  # Quote without depth
kws.MODE_FULL   # Full with depth
```

---

## Threaded Mode

For non-blocking operation:

```python
# Start in background thread
kws.connect(threaded=True)

# Main thread continues
while True:
    if kws.is_connected():
        print("Connected and receiving data")
    time.sleep(1)
```

---

## Best Practices

1. **Use appropriate mode**: Use LTP for simple tracking, Full only when depth needed
2. **Handle reconnection**: Implement `on_reconnect` and `on_noreconnect`
3. **Check message type**: Binary = market data, Text = postbacks
4. **Limit subscriptions**: Max 3000 per connection, 3 connections per API key
5. **Process ticks efficiently**: Heavy processing should be async/queued
6. **Store tokens locally**: Don't call instruments API for token lookup during ticks

---

## Common Issues

| Issue               | Solution                                  |
| ------------------- | ----------------------------------------- |
| Connection drops    | Check internet, implement reconnection    |
| Missing ticks       | Verify subscription, check mode           |
| High latency        | Reduce subscriptions, optimize processing |
| Binary parse errors | Use SDK, verify packet structure          |

---

_Last Updated: December 2025_
