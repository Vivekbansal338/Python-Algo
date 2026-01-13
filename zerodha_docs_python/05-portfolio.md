# Kite Connect API - Portfolio (Holdings & Positions)

## Overview

The Portfolio API provides access to user's long-term holdings and short-term positions, with real-time profit/loss calculations.

---

## API Endpoints

| Method | Endpoint                        | Description                 |
| ------ | ------------------------------- | --------------------------- |
| `GET`  | `/portfolio/holdings`           | Get equity holdings         |
| `GET`  | `/portfolio/holdings/auctions`  | Get auction holdings        |
| `GET`  | `/portfolio/positions`          | Get day/overnight positions |
| `PUT`  | `/portfolio/positions`          | Convert position product    |
| `POST` | `/portfolio/holdings/authorise` | Initiate CDSL authorisation |

---

## Holdings

Holdings contain long-term equity delivery stocks in the user's DEMAT account. They remain until sold, delisted, or changed by exchanges.

### Get Holdings

```bash
curl "https://api.kite.trade/portfolio/holdings" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": [
    {
      "tradingsymbol": "SBIN",
      "exchange": "BSE",
      "instrument_token": 128028676,
      "isin": "INE062A01020",
      "product": "CNC",
      "price": 0,
      "quantity": 16,
      "used_quantity": 0,
      "t1_quantity": 0,
      "realised_quantity": 16,
      "authorised_quantity": 0,
      "authorised_date": "2025-01-17 00:00:00",
      "authorisation": {},
      "opening_quantity": 16,
      "short_quantity": 0,
      "collateral_quantity": 0,
      "collateral_type": "",
      "discrepancy": false,
      "average_price": 801.78,
      "last_price": 762.45,
      "close_price": 766.4,
      "pnl": -629.3,
      "day_change": -3.95,
      "day_change_percentage": -0.515,
      "mtf": {
        "quantity": 0,
        "used_quantity": 0,
        "average_price": 0,
        "value": 0,
        "initial_margin": 0
      }
    }
  ]
}
```

### Holdings Attributes

| Attribute               | Type   | Description                       |
| ----------------------- | ------ | --------------------------------- |
| `tradingsymbol`         | string | Exchange trading symbol           |
| `exchange`              | string | Exchange (NSE/BSE)                |
| `instrument_token`      | int    | Token for WebSocket subscription  |
| `isin`                  | string | Standard ISIN for the stock       |
| `product`               | string | Product type (CNC)                |
| `quantity`              | int    | Total quantity held (T+2 settled) |
| `t1_quantity`           | int    | Quantity on T+1 (not yet settled) |
| `realised_quantity`     | int    | Quantity delivered to Demat       |
| `used_quantity`         | int    | Quantity sold today               |
| `authorised_quantity`   | int    | Quantity authorised for sale      |
| `opening_quantity`      | int    | Quantity at day start             |
| `average_price`         | float  | Average buy price                 |
| `last_price`            | float  | Last traded price                 |
| `close_price`           | float  | Previous day close                |
| `pnl`                   | float  | Profit/Loss                       |
| `day_change`            | float  | Absolute change today             |
| `day_change_percentage` | float  | Percentage change today           |
| `collateral_quantity`   | int    | Quantity pledged as collateral    |
| `collateral_type`       | string | Type of collateral                |
| `discrepancy`           | bool   | Price discrepancy flag            |

### MTF (Margin Trading Facility) Sub-object

| Attribute        | Description             |
| ---------------- | ----------------------- |
| `quantity`       | MTF holdings quantity   |
| `used_quantity`  | MTF quantity used       |
| `average_price`  | MTF average price       |
| `value`          | MTF holdings value      |
| `initial_margin` | Initial margin required |

---

## Auction Holdings

Get holdings available for auction participation:

```bash
curl "https://api.kite.trade/portfolio/holdings/auctions" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

Response includes additional `auction_number` field for placing auction orders.

---

## Positions

Positions contain short to medium-term derivatives and intraday equity trades. They include both `net` (actual positions) and `day` (today's trading activity).

### Get Positions

```bash
curl "https://api.kite.trade/portfolio/positions" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": {
    "net": [
      {
        "tradingsymbol": "NIFTY25JANFUT",
        "exchange": "NFO",
        "instrument_token": 53496327,
        "product": "NRML",
        "quantity": 75,
        "overnight_quantity": 0,
        "multiplier": 1,
        "average_price": 24150.5,
        "close_price": 24100,
        "last_price": 24200,
        "value": -1811287.5,
        "pnl": 3712.5,
        "m2m": 7500,
        "unrealised": 3712.5,
        "realised": 0,
        "buy_quantity": 75,
        "buy_price": 24150.5,
        "buy_value": 1811287.5,
        "buy_m2m": 1811287.5,
        "sell_quantity": 0,
        "sell_price": 0,
        "sell_value": 0,
        "sell_m2m": 0,
        "day_buy_quantity": 75,
        "day_buy_price": 24150.5,
        "day_buy_value": 1811287.5,
        "day_sell_quantity": 0,
        "day_sell_price": 0,
        "day_sell_value": 0
      }
    ],
    "day": [
      {
        "tradingsymbol": "SBIN",
        "exchange": "NSE",
        "instrument_token": 779521,
        "product": "MIS",
        "quantity": 0,
        "overnight_quantity": 0,
        "multiplier": 1,
        "average_price": 0,
        "close_price": 0,
        "last_price": 760,
        "value": -500,
        "pnl": -500,
        "m2m": -500,
        "unrealised": -500,
        "realised": 0,
        "buy_quantity": 10,
        "buy_price": 765,
        "buy_value": 7650,
        "buy_m2m": 7650,
        "sell_quantity": 10,
        "sell_price": 715,
        "sell_value": 7150,
        "sell_m2m": 7150,
        "day_buy_quantity": 10,
        "day_buy_price": 765,
        "day_buy_value": 7650,
        "day_sell_quantity": 10,
        "day_sell_price": 715,
        "day_sell_value": 7150
      }
    ]
  }
}
```

### Position Attributes

| Attribute            | Type   | Description                 |
| -------------------- | ------ | --------------------------- |
| `tradingsymbol`      | string | Trading symbol              |
| `exchange`           | string | Exchange                    |
| `instrument_token`   | int    | Token for WebSocket         |
| `product`            | string | Product type (NRML/MIS)     |
| `quantity`           | int    | Net quantity                |
| `overnight_quantity` | int    | Carried forward quantity    |
| `multiplier`         | int    | Lot size multiplier for P&L |
| `average_price`      | float  | Net position average price  |
| `close_price`        | float  | Previous day close          |
| `last_price`         | float  | Last traded price           |
| `value`              | float  | Net position value          |
| `pnl`                | float  | Net profit/loss             |
| `m2m`                | float  | Mark to market P&L          |
| `unrealised`         | float  | Unrealised intraday P&L     |
| `realised`           | float  | Realised intraday P&L       |

### Buy/Sell Breakdown

| Attribute       | Description         |
| --------------- | ------------------- |
| `buy_quantity`  | Total buy quantity  |
| `buy_price`     | Average buy price   |
| `buy_value`     | Total buy value     |
| `buy_m2m`       | Buy side M2M        |
| `sell_quantity` | Total sell quantity |
| `sell_price`    | Average sell price  |
| `sell_value`    | Total sell value    |
| `sell_m2m`      | Sell side M2M       |

### Day Position Breakdown

| Attribute           | Description                |
| ------------------- | -------------------------- |
| `day_buy_quantity`  | Today's buy quantity       |
| `day_buy_price`     | Today's average buy price  |
| `day_buy_value`     | Today's buy value          |
| `day_sell_quantity` | Today's sell quantity      |
| `day_sell_price`    | Today's average sell price |
| `day_sell_value`    | Today's sell value         |

---

## Position Conversion

Convert an open position between margin products:

```bash
curl -X PUT https://api.kite.trade/portfolio/positions \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "tradingsymbol=NIFTY25JANFUT" \
  -d "exchange=NFO" \
  -d "transaction_type=BUY" \
  -d "position_type=day" \
  -d "quantity=75" \
  -d "old_product=MIS" \
  -d "new_product=NRML"
```

### Parameters

| Parameter          | Description                |
| ------------------ | -------------------------- |
| `tradingsymbol`    | Trading symbol             |
| `exchange`         | Exchange                   |
| `transaction_type` | BUY or SELL                |
| `position_type`    | `day` or `overnight`       |
| `quantity`         | Quantity to convert        |
| `old_product`      | Current product (MIS/NRML) |
| `new_product`      | Target product (NRML/MIS)  |

### Response

```json
{
  "status": "success",
  "data": true
}
```

---

## Exiting Positions

There's no special "exit" API. To exit:

1. Place an opposite order (BUY if you're short, SELL if you're long)
2. Use MARKET order for immediate exit
3. **Important**: Use the same product type as the existing position

```python
# Exit a long position
kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NFO,
    tradingsymbol="NIFTY25JANFUT",
    transaction_type=kite.TRANSACTION_TYPE_SELL,  # Opposite of position
    quantity=75,
    order_type=kite.ORDER_TYPE_MARKET,
    product=kite.PRODUCT_NRML  # Same as position product
)
```

---

## Holdings Authorisation (CDSL eDIS)

When selling equity holdings without PoA, electronic authorisation at CDSL is required.

### Flow

1. Attempt sell order
2. If HTTP 428 returned, authorisation needed
3. Initiate authorisation request
4. Redirect user to CDSL portal
5. User enters Demat PIN
6. Retry sell order

### Initiate Authorisation

```bash
curl -X POST https://api.kite.trade/portfolio/holdings/authorise \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "isin=INE002A01018" \
  -d "quantity=50" \
  -d "isin=INE009A01021" \
  -d "quantity=50"
```

### Response

```json
{
  "status": "success",
  "data": {
    "request_id": "na8QgCeQm05UHG6NL9sAGRzdfSF64UdB"
  }
}
```

### Redirect URL

```
https://kite.zerodha.com/connect/portfolio/authorise/holdings/:api_key/:request_id
```

After completion, user is redirected to:

```
/connect/portfolio/authorise/holdings/:api_key/:request_id/finish?status=success
```

---

## Python Examples

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Get holdings
holdings = kite.holdings()
for h in holdings:
    print(f"{h['tradingsymbol']}: {h['quantity']} @ {h['average_price']} | P&L: {h['pnl']}")

# Get positions
positions = kite.positions()

# Net positions
for p in positions['net']:
    print(f"{p['tradingsymbol']}: {p['quantity']} | P&L: {p['pnl']}")

# Day positions
for p in positions['day']:
    print(f"{p['tradingsymbol']}: Day P&L: {p['pnl']}")

# Convert position
kite.convert_position(
    exchange=kite.EXCHANGE_NFO,
    tradingsymbol="NIFTY25JANFUT",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    position_type=kite.POSITION_TYPE_DAY,
    quantity=75,
    old_product=kite.PRODUCT_MIS,
    new_product=kite.PRODUCT_NRML
)
```

---

## Key Differences: Holdings vs Positions

| Aspect         | Holdings                | Positions              |
| -------------- | ----------------------- | ---------------------- |
| **Duration**   | Long-term (until sold)  | Intraday/Short-term    |
| **Settlement** | T+1/T+2 in Demat        | Same day or overnight  |
| **Products**   | CNC only                | MIS, NRML              |
| **Segments**   | Equity only             | Equity, F&O, Commodity |
| **Expiry**     | Never (unless delisted) | Contract expiry (F&O)  |

---

## Important Notes

1. **T+1 Holdings**: Not available for immediate sale
2. **Product Matching**: Exit orders must use same product as position
3. **M2M Calculation**: Based on previous close price
4. **Overnight Positions**: Equity MIS positions auto-squared off
5. **Authorisation**: Required for selling holdings without PoA

---

_Last Updated: December 2025_
