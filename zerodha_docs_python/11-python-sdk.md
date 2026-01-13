# Kite Connect Python SDK Reference

## Installation

```bash
pip install kiteconnect
```

---

## KiteConnect Class

The main class for REST API interactions.

### Initialization

```python
from kiteconnect import KiteConnect

kite = KiteConnect(
    api_key="your_api_key",
    access_token="your_access_token",  # Optional at init
    root="https://api.kite.trade",     # Optional
    debug=False,                        # Optional
    timeout=7,                          # Optional (seconds)
    pool=None,                          # Optional
    proxies=None                        # Optional
)
```

### Constructor Parameters

| Parameter      | Type                | Description                  |
| -------------- | ------------------- | ---------------------------- |
| `api_key`      | str                 | Your Kite Connect API key    |
| `access_token` | str                 | Access token (can set later) |
| `root`         | str                 | API base URL                 |
| `debug`        | bool                | Enable debug logging         |
| `timeout`      | int                 | Request timeout in seconds   |
| `pool`         | urllib3.PoolManager | Custom connection pool       |
| `proxies`      | dict                | Proxy configuration          |

---

## Authentication Methods

### login_url()

Get the login URL for user authentication.

```python
login_url = kite.login_url()
# Returns: https://kite.zerodha.com/connect/login?v=3&api_key=xxx
```

### generate_session(request_token, api_secret)

Exchange request token for access token.

```python
data = kite.generate_session(
    request_token="request_token_from_redirect",
    api_secret="your_api_secret"
)

access_token = data["access_token"]
kite.set_access_token(access_token)
```

**Returns:**

```python
{
    "user_id": "AB1234",
    "user_name": "John Doe",
    "email": "john@example.com",
    "user_type": "individual",
    "broker": "ZERODHA",
    "access_token": "xxxx",
    "public_token": "xxxx",
    "refresh_token": "",
    "enctoken": "xxxx",
    "login_time": "2025-01-15 09:00:00",
    "exchanges": ["NSE", "BSE", "NFO", "MCX"],
    "products": ["CNC", "NRML", "MIS"],
    "order_types": ["MARKET", "LIMIT", "SL", "SL-M"]
}
```

### set_access_token(access_token)

Set access token after generation.

```python
kite.set_access_token("access_token_value")
```

### invalidate_access_token(access_token=None)

Logout and invalidate the session.

```python
kite.invalidate_access_token()
```

---

## User Methods

### profile()

Get user profile.

```python
profile = kite.profile()
```

### margins(segment=None)

Get account margins.

```python
# All segments
margins = kite.margins()

# Specific segment
equity_margins = kite.margins(segment="equity")
commodity_margins = kite.margins(segment="commodity")
```

---

## Order Methods

### place_order(variety, exchange, tradingsymbol, transaction_type, quantity, ...)

Place a new order.

```python
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="SBIN",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    product=kite.PRODUCT_CNC,
    order_type=kite.ORDER_TYPE_MARKET,
    price=None,
    trigger_price=None,
    validity=kite.VALIDITY_DAY,
    disclosed_quantity=None,
    tag="my_tag"
)
```

**Parameters:**

| Parameter            | Type  | Required | Description                        |
| -------------------- | ----- | -------- | ---------------------------------- |
| `variety`            | str   | Yes      | regular, amo, co, iceberg, auction |
| `exchange`           | str   | Yes      | NSE, BSE, NFO, CDS, BCD, MCX       |
| `tradingsymbol`      | str   | Yes      | Trading symbol                     |
| `transaction_type`   | str   | Yes      | BUY or SELL                        |
| `quantity`           | int   | Yes      | Order quantity                     |
| `product`            | str   | Yes      | CNC, NRML, MIS                     |
| `order_type`         | str   | Yes      | MARKET, LIMIT, SL, SL-M            |
| `price`              | float | No       | Limit price (for LIMIT/SL)         |
| `trigger_price`      | float | No       | Trigger price (for SL/SL-M)        |
| `validity`           | str   | No       | DAY, IOC, TTL                      |
| `validity_ttl`       | int   | No       | Minutes for TTL validity           |
| `disclosed_quantity` | int   | No       | Disclosed quantity                 |
| `tag`                | str   | No       | Custom tag (max 20 chars)          |
| `iceberg_legs`       | int   | No       | Number of iceberg legs             |
| `iceberg_quantity`   | int   | No       | Quantity per leg                   |
| `auction_number`     | str   | No       | Auction number                     |

### modify_order(variety, order_id, ...)

Modify an existing order.

```python
kite.modify_order(
    variety=kite.VARIETY_REGULAR,
    order_id="220303000308932",
    quantity=2,
    price=470.0,
    order_type=kite.ORDER_TYPE_LIMIT
)
```

### cancel_order(variety, order_id, parent_order_id=None)

Cancel an order.

```python
kite.cancel_order(
    variety=kite.VARIETY_REGULAR,
    order_id="220303000308932"
)
```

### orders()

Get list of all orders for the day.

```python
orders = kite.orders()
```

### order_history(order_id)

Get order history (all status changes).

```python
history = kite.order_history(order_id="220303000308932")
```

### trades()

Get list of all trades for the day.

```python
trades = kite.trades()
```

### order_trades(order_id)

Get trades for a specific order.

```python
order_trades = kite.order_trades(order_id="220303000308932")
```

---

## GTT Methods

### place_gtt(trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)

Place a GTT order.

```python
# Single trigger GTT
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="SBIN",
    exchange=kite.EXCHANGE_NSE,
    trigger_values=[350],
    last_price=400,
    orders=[{
        "transaction_type": kite.TRANSACTION_TYPE_BUY,
        "quantity": 10,
        "price": 350,
        "order_type": kite.ORDER_TYPE_LIMIT,
        "product": kite.PRODUCT_CNC
    }]
)

# Two-leg GTT (OCO)
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_OCO,
    tradingsymbol="SBIN",
    exchange=kite.EXCHANGE_NSE,
    trigger_values=[340, 450],  # Stop-loss, Target
    last_price=400,
    orders=[
        {
            "transaction_type": kite.TRANSACTION_TYPE_SELL,
            "quantity": 10,
            "price": 340,
            "order_type": kite.ORDER_TYPE_LIMIT,
            "product": kite.PRODUCT_CNC
        },
        {
            "transaction_type": kite.TRANSACTION_TYPE_SELL,
            "quantity": 10,
            "price": 450,
            "order_type": kite.ORDER_TYPE_LIMIT,
            "product": kite.PRODUCT_CNC
        }
    ]
)
```

### modify_gtt(trigger_id, trigger_type, tradingsymbol, exchange, trigger_values, last_price, orders)

Modify an existing GTT.

```python
kite.modify_gtt(
    trigger_id=123456,
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="SBIN",
    exchange=kite.EXCHANGE_NSE,
    trigger_values=[355],
    last_price=400,
    orders=[...]
)
```

### delete_gtt(trigger_id)

Delete a GTT.

```python
kite.delete_gtt(trigger_id=123456)
```

### get_gtts()

Get list of all GTTs.

```python
gtts = kite.get_gtts()
```

### get_gtt(trigger_id)

Get details of a specific GTT.

```python
gtt = kite.get_gtt(trigger_id=123456)
```

---

## Portfolio Methods

### holdings()

Get holdings (delivery stocks).

```python
holdings = kite.holdings()
```

### positions()

Get all positions.

```python
positions = kite.positions()
# Returns: {"net": [...], "day": [...]}
```

### convert_position(exchange, tradingsymbol, transaction_type, position_type, quantity, old_product, new_product)

Convert position from one product to another.

```python
kite.convert_position(
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="SBIN",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    position_type=kite.POSITION_TYPE_DAY,
    quantity=5,
    old_product=kite.PRODUCT_MIS,
    new_product=kite.PRODUCT_CNC
)
```

---

## Market Data Methods

### instruments(exchange=None)

Download instruments master file.

```python
# All instruments
instruments = kite.instruments()

# Exchange-specific
nse_instruments = kite.instruments(exchange=kite.EXCHANGE_NSE)
nfo_instruments = kite.instruments(exchange=kite.EXCHANGE_NFO)
```

### quote(instruments)

Get full quote for instruments.

```python
quotes = kite.quote(["NSE:SBIN", "NSE:RELIANCE", 256265])
```

### ohlc(instruments)

Get OHLC data only.

```python
ohlc = kite.ohlc(["NSE:SBIN", "NSE:RELIANCE"])
```

### ltp(instruments)

Get only last traded price.

```python
ltp = kite.ltp(["NSE:SBIN"])
# Returns: {"NSE:SBIN": {"instrument_token": 779521, "last_price": 470.5}}
```

---

## Historical Data Methods

### historical_data(instrument_token, from_date, to_date, interval, continuous=False, oi=False)

Get historical OHLCV data.

```python
from datetime import datetime, timedelta

# Get last 10 days of daily data
data = kite.historical_data(
    instrument_token=779521,
    from_date=datetime.now() - timedelta(days=10),
    to_date=datetime.now(),
    interval="day"
)

# Get intraday 5-minute candles
data = kite.historical_data(
    instrument_token=779521,
    from_date=datetime.now() - timedelta(days=1),
    to_date=datetime.now(),
    interval="5minute"
)

# Continuous futures with OI
data = kite.historical_data(
    instrument_token=11794434,
    from_date=datetime(2025, 1, 1),
    to_date=datetime(2025, 1, 15),
    interval="day",
    continuous=True,
    oi=True
)
```

**Intervals:** `minute`, `day`, `3minute`, `5minute`, `10minute`, `15minute`, `30minute`, `60minute`

**Returns:**

```python
[
    {
        "date": datetime(2025, 1, 15, 9, 15),
        "open": 468.0,
        "high": 472.0,
        "low": 467.5,
        "close": 470.5,
        "volume": 125000
    },
    ...
]
```

---

## Margin Methods

### order_margins(orders)

Calculate margins for orders before placing.

```python
margins = kite.order_margins([
    {
        "exchange": "NSE",
        "tradingsymbol": "SBIN",
        "transaction_type": "BUY",
        "variety": "regular",
        "product": "CNC",
        "order_type": "MARKET",
        "quantity": 100
    }
])
```

### basket_margins(orders, consider_positions=True, mode=None)

Calculate margins for basket of orders.

```python
margins = kite.basket_margins(
    orders=[...],
    consider_positions=True,
    mode="compact"
)
```

---

## Constants

The KiteConnect class provides these constants:

```python
# Exchanges
kite.EXCHANGE_NSE = "NSE"
kite.EXCHANGE_BSE = "BSE"
kite.EXCHANGE_NFO = "NFO"
kite.EXCHANGE_CDS = "CDS"
kite.EXCHANGE_BCD = "BCD"
kite.EXCHANGE_MCX = "MCX"

# Products
kite.PRODUCT_CNC = "CNC"
kite.PRODUCT_NRML = "NRML"
kite.PRODUCT_MIS = "MIS"

# Order types
kite.ORDER_TYPE_MARKET = "MARKET"
kite.ORDER_TYPE_LIMIT = "LIMIT"
kite.ORDER_TYPE_SL = "SL"
kite.ORDER_TYPE_SLM = "SL-M"

# Transaction types
kite.TRANSACTION_TYPE_BUY = "BUY"
kite.TRANSACTION_TYPE_SELL = "SELL"

# Varieties
kite.VARIETY_REGULAR = "regular"
kite.VARIETY_AMO = "amo"
kite.VARIETY_CO = "co"
kite.VARIETY_ICEBERG = "iceberg"
kite.VARIETY_AUCTION = "auction"

# Validity
kite.VALIDITY_DAY = "DAY"
kite.VALIDITY_IOC = "IOC"
kite.VALIDITY_TTL = "TTL"

# Position types
kite.POSITION_TYPE_DAY = "day"
kite.POSITION_TYPE_OVERNIGHT = "overnight"

# GTT types
kite.GTT_TYPE_SINGLE = "single"
kite.GTT_TYPE_OCO = "two-leg"

# Margins segments
kite.MARGIN_EQUITY = "equity"
kite.MARGIN_COMMODITY = "commodity"
```

---

## KiteTicker Class

WebSocket client for real-time market data.

### Initialization

```python
from kiteconnect import KiteTicker

kws = KiteTicker(
    api_key="your_api_key",
    access_token="your_access_token",
    debug=False,
    root="wss://ws.kite.trade",
    reconnect=True,
    reconnect_max_tries=50,
    reconnect_max_delay=60,
    connect_timeout=30
)
```

### Constructor Parameters

| Parameter             | Type | Default             | Description                  |
| --------------------- | ---- | ------------------- | ---------------------------- |
| `api_key`             | str  | -                   | Your API key                 |
| `access_token`        | str  | -                   | Access token                 |
| `debug`               | bool | False               | Enable debug logging         |
| `root`                | str  | wss://ws.kite.trade | WebSocket URL                |
| `reconnect`           | bool | True                | Auto-reconnect on disconnect |
| `reconnect_max_tries` | int  | 50                  | Max reconnection attempts    |
| `reconnect_max_delay` | int  | 60                  | Max delay between reconnects |
| `connect_timeout`     | int  | 30                  | Connection timeout           |

---

## KiteTicker Callbacks

### on_ticks(ws, ticks)

Called when tick data is received.

```python
def on_ticks(ws, ticks):
    for tick in ticks:
        print(f"{tick['instrument_token']}: {tick['last_price']}")

kws.on_ticks = on_ticks
```

### on_connect(ws, response)

Called on successful connection.

```python
def on_connect(ws, response):
    print("Connected!")
    ws.subscribe([256265, 779521])
    ws.set_mode(ws.MODE_FULL, [256265])

kws.on_connect = on_connect
```

### on_close(ws, code, reason)

Called when connection is closed.

```python
def on_close(ws, code, reason):
    print(f"Closed: {code} - {reason}")

kws.on_close = on_close
```

### on_error(ws, code, reason)

Called on error.

```python
def on_error(ws, code, reason):
    print(f"Error: {code} - {reason}")

kws.on_error = on_error
```

### on_reconnect(ws, attempts)

Called on reconnection attempt.

```python
def on_reconnect(ws, attempts):
    print(f"Reconnecting... attempt {attempts}")

kws.on_reconnect = on_reconnect
```

### on_noreconnect(ws)

Called when max reconnect attempts exhausted.

```python
def on_noreconnect(ws):
    print("Max reconnect attempts reached")

kws.on_noreconnect = on_noreconnect
```

### on_order_update(ws, data)

Called when order status changes.

```python
def on_order_update(ws, data):
    print(f"Order {data['order_id']}: {data['status']}")

kws.on_order_update = on_order_update
```

---

## KiteTicker Methods

### connect(threaded=False, disable_ssl_verification=False, proxy=None)

Connect to WebSocket.

```python
# Blocking connect
kws.connect()

# Threaded connect (non-blocking)
kws.connect(threaded=True)
```

### close(code=None, reason=None)

Close WebSocket connection.

```python
kws.close()
```

### subscribe(instrument_tokens)

Subscribe to instruments.

```python
kws.subscribe([256265, 779521, 341249])
```

### unsubscribe(instrument_tokens)

Unsubscribe from instruments.

```python
kws.unsubscribe([256265])
```

### set_mode(mode, instrument_tokens)

Set streaming mode for instruments.

```python
# Available modes
kws.MODE_LTP   # Only last price
kws.MODE_QUOTE # LTP + OHLC + volume
kws.MODE_FULL  # Full market depth

# Set mode
kws.set_mode(kws.MODE_FULL, [256265])
kws.set_mode(kws.MODE_LTP, [779521, 341249])
```

---

## Tick Structure

### MODE_LTP

```python
{
    "mode": "ltp",
    "instrument_token": 256265,
    "tradable": True,
    "last_price": 17500.50
}
```

### MODE_QUOTE

```python
{
    "mode": "quote",
    "instrument_token": 256265,
    "tradable": True,
    "last_price": 17500.50,
    "last_quantity": 50,
    "average_price": 17485.25,
    "volume": 12500000,
    "buy_quantity": 250000,
    "sell_quantity": 180000,
    "ohlc": {
        "open": 17450.0,
        "high": 17550.0,
        "low": 17420.0,
        "close": 17480.0
    },
    "change": 20.50
}
```

### MODE_FULL (Indices)

```python
{
    "mode": "full",
    "instrument_token": 256265,
    "tradable": False,  # Indices are not tradable
    "last_price": 17500.50,
    "ohlc": {...},
    "change": 20.50
}
```

### MODE_FULL (Equity/F&O)

```python
{
    "mode": "full",
    "instrument_token": 779521,
    "tradable": True,
    "last_price": 470.50,
    "last_quantity": 100,
    "last_trade_time": datetime(2025, 1, 15, 15, 29, 45),
    "average_price": 468.25,
    "volume": 5000000,
    "buy_quantity": 50000,
    "sell_quantity": 45000,
    "ohlc": {
        "open": 465.0,
        "high": 472.0,
        "low": 464.0,
        "close": 466.5
    },
    "change": 4.0,
    "oi": 0,  # For F&O
    "oi_day_high": 0,
    "oi_day_low": 0,
    "exchange_timestamp": datetime(2025, 1, 15, 15, 29, 45),
    "depth": {
        "buy": [
            {"price": 470.45, "quantity": 500, "orders": 5},
            {"price": 470.40, "quantity": 1200, "orders": 12},
            {"price": 470.35, "quantity": 800, "orders": 8},
            {"price": 470.30, "quantity": 650, "orders": 6},
            {"price": 470.25, "quantity": 1500, "orders": 15}
        ],
        "sell": [
            {"price": 470.50, "quantity": 400, "orders": 4},
            {"price": 470.55, "quantity": 900, "orders": 9},
            {"price": 470.60, "quantity": 750, "orders": 7},
            {"price": 470.65, "quantity": 1100, "orders": 11},
            {"price": 470.70, "quantity": 600, "orders": 6}
        ]
    }
}
```

---

## Complete Example

```python
from kiteconnect import KiteConnect, KiteTicker
import pandas as pd
from datetime import datetime, timedelta

# Initialize KiteConnect
kite = KiteConnect(api_key="your_api_key")

# Step 1: Get login URL
print(f"Login URL: {kite.login_url()}")

# Step 2: After user logs in and you get request_token
request_token = "received_request_token"
data = kite.generate_session(request_token, api_secret="your_api_secret")
kite.set_access_token(data["access_token"])

# Step 3: Fetch instruments and create lookup
instruments = kite.instruments("NSE")
instrument_df = pd.DataFrame(instruments)
token_lookup = dict(zip(instrument_df.tradingsymbol, instrument_df.instrument_token))

# Step 4: Place an order
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="SBIN",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    product=kite.PRODUCT_CNC,
    order_type=kite.ORDER_TYPE_MARKET
)
print(f"Order placed: {order_id}")

# Step 5: Get historical data
historical = kite.historical_data(
    instrument_token=token_lookup["SBIN"],
    from_date=datetime.now() - timedelta(days=30),
    to_date=datetime.now(),
    interval="day"
)
df = pd.DataFrame(historical)
print(df.tail())

# Step 6: Setup WebSocket for live data
kws = KiteTicker(api_key="your_api_key", access_token=data["access_token"])

def on_ticks(ws, ticks):
    for tick in ticks:
        print(f"Token: {tick['instrument_token']}, LTP: {tick['last_price']}")

def on_connect(ws, response):
    ws.subscribe([token_lookup["SBIN"], token_lookup["RELIANCE"]])
    ws.set_mode(ws.MODE_QUOTE, [token_lookup["SBIN"]])

def on_order_update(ws, data):
    print(f"Order Update: {data['order_id']} - {data['status']}")

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_order_update = on_order_update

# Connect (blocking)
kws.connect()
```

---

## Exception Handling

```python
from kiteconnect import KiteConnect
from kiteconnect.exceptions import (
    KiteException,
    GeneralException,
    TokenException,
    PermissionException,
    OrderException,
    InputException,
    DataException,
    NetworkException
)

kite = KiteConnect(api_key="xxx")

try:
    order_id = kite.place_order(...)
except TokenException as e:
    print(f"Session expired: {e}")
    # Re-login
except OrderException as e:
    print(f"Order error: {e}")
    # Handle order failure
except InputException as e:
    print(f"Invalid input: {e}")
    # Fix input parameters
except NetworkException as e:
    print(f"Network error: {e}")
    # Retry
except KiteException as e:
    print(f"General Kite error: {e}")
```

---

## Threaded WebSocket

```python
import time
from kiteconnect import KiteTicker

kws = KiteTicker(api_key="xxx", access_token="xxx")

def on_ticks(ws, ticks):
    print(ticks)

def on_connect(ws, response):
    ws.subscribe([256265])

kws.on_ticks = on_ticks
kws.on_connect = on_connect

# Non-blocking connect
kws.connect(threaded=True)

# Main thread continues
while True:
    time.sleep(1)
    # Do other things
```

---

_Last Updated: December 2025_
