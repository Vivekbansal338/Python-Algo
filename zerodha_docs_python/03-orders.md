# Kite Connect API - Orders

## Overview

The Orders API allows you to place, modify, cancel, and retrieve orders across different varieties and segments.

---

## API Endpoints

| Method   | Endpoint                     | Description                |
| -------- | ---------------------------- | -------------------------- |
| `POST`   | `/orders/:variety`           | Place an order             |
| `PUT`    | `/orders/:variety/:order_id` | Modify an order            |
| `DELETE` | `/orders/:variety/:order_id` | Cancel an order            |
| `GET`    | `/orders`                    | Get all orders for the day |
| `GET`    | `/orders/:order_id`          | Get order history          |
| `GET`    | `/trades`                    | Get all executed trades    |
| `GET`    | `/orders/:order_id/trades`   | Get trades for an order    |

---

## Constants & Enums

### Order Varieties

| Variety   | Description        |
| --------- | ------------------ |
| `regular` | Regular order      |
| `amo`     | After Market Order |
| `co`      | Cover Order        |
| `iceberg` | Iceberg Order      |
| `auction` | Auction Order      |

### Order Types

| Type     | Description                          |
| -------- | ------------------------------------ |
| `MARKET` | Execute at best available price      |
| `LIMIT`  | Execute at specified price or better |
| `SL`     | Stoploss limit order                 |
| `SL-M`   | Stoploss market order                |

### Products (Margin Types)

| Product | Description                        |
| ------- | ---------------------------------- |
| `CNC`   | Cash & Carry (delivery for equity) |
| `NRML`  | Normal (F&O overnight positions)   |
| `MIS`   | Margin Intraday Squareoff          |
| `MTF`   | Margin Trading Facility            |

### Transaction Types

| Type   | Description      |
| ------ | ---------------- |
| `BUY`  | Buy transaction  |
| `SELL` | Sell transaction |

### Validity

| Validity | Description                    |
| -------- | ------------------------------ |
| `DAY`    | Valid for the trading day      |
| `IOC`    | Immediate or Cancel            |
| `TTL`    | Time to Live (specify minutes) |

### Exchanges

| Exchange | Description              |
| -------- | ------------------------ |
| `NSE`    | National Stock Exchange  |
| `BSE`    | Bombay Stock Exchange    |
| `NFO`    | NSE Futures & Options    |
| `BFO`    | BSE Futures & Options    |
| `MCX`    | Multi Commodity Exchange |
| `CDS`    | Currency Derivatives     |
| `BCD`    | BSE Currency Derivatives |

---

## Placing Orders

### Regular Order

```bash
curl https://api.kite.trade/orders/regular \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "tradingsymbol=SBIN" \
  -d "exchange=NSE" \
  -d "transaction_type=BUY" \
  -d "order_type=MARKET" \
  -d "quantity=1" \
  -d "product=CNC" \
  -d "validity=DAY"
```

### Response

```json
{
  "status": "success",
  "data": {
    "order_id": "220303000308932"
  }
}
```

### Order Parameters

| Parameter            | Required  | Description                    |
| -------------------- | --------- | ------------------------------ |
| `tradingsymbol`      | Yes       | Exchange trading symbol        |
| `exchange`           | Yes       | Exchange (NSE, BSE, NFO, etc.) |
| `transaction_type`   | Yes       | BUY or SELL                    |
| `order_type`         | Yes       | MARKET, LIMIT, SL, SL-M        |
| `quantity`           | Yes       | Quantity to trade              |
| `product`            | Yes       | CNC, NRML, MIS, MTF            |
| `price`              | For LIMIT | Price for limit orders         |
| `trigger_price`      | For SL    | Trigger price for stoploss     |
| `validity`           | No        | DAY, IOC, TTL (default: DAY)   |
| `validity_ttl`       | For TTL   | Minutes for TTL validity       |
| `disclosed_quantity` | No        | Quantity to disclose (equity)  |
| `tag`                | No        | Custom tag (max 20 chars)      |
| `iceberg_legs`       | Iceberg   | Number of legs (2-10)          |
| `iceberg_quantity`   | Iceberg   | Quantity per leg               |
| `market_protection`  | No        | Protection % for MARKET/SL-M   |
| `autoslice`          | No        | Auto-slice for freeze quantity |

---

## Market Protection

Protects against extreme price movements for MARKET and SL-M orders:

| Value   | Meaning                      |
| ------- | ---------------------------- |
| `0`     | No protection (default)      |
| `1-100` | Custom protection percentage |
| `-1`    | Automatic protection         |

---

## Auto Slice Orders

When quantity exceeds freeze limits, set `autoslice=true` to automatically split orders:

```bash
-d "autoslice=true"
```

Orders are tagged with `autoslice` and child slices have `autoslice:parent_order_id` tag.

---

## Modifying Orders

Modify open/pending orders:

```bash
curl -X PUT https://api.kite.trade/orders/regular/220303000308932 \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "order_type=LIMIT" \
  -d "price=750" \
  -d "quantity=2" \
  -d "validity=DAY"
```

### Modifiable Parameters

| Parameter            | Description          |
| -------------------- | -------------------- |
| `order_type`         | Change order type    |
| `quantity`           | Change quantity      |
| `price`              | Change limit price   |
| `trigger_price`      | Change trigger price |
| `disclosed_quantity` | Change disclosed qty |
| `validity`           | Change validity      |

> **Note**: Max 25 modifications per order. After that, cancel and re-place.

---

## Cancelling Orders

```bash
curl -X DELETE \
  "https://api.kite.trade/orders/regular/220303000308932" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": {
    "order_id": "220303000308932"
  }
}
```

---

## Retrieving Orders

### Get All Orders

```bash
curl https://api.kite.trade/orders \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": [
    {
      "order_id": "220303000308932",
      "exchange_order_id": "1300000029561105",
      "parent_order_id": null,
      "status": "COMPLETE",
      "status_message": null,
      "order_timestamp": "2025-01-17 11:49:45",
      "exchange_timestamp": "2025-01-17 11:49:45",
      "exchange_update_timestamp": "2025-01-17 11:49:45",
      "variety": "regular",
      "modified": false,
      "exchange": "NSE",
      "tradingsymbol": "SBIN",
      "instrument_token": 779521,
      "order_type": "MARKET",
      "transaction_type": "BUY",
      "validity": "DAY",
      "product": "CNC",
      "quantity": 1,
      "disclosed_quantity": 0,
      "price": 0,
      "trigger_price": 0,
      "average_price": 470,
      "filled_quantity": 1,
      "pending_quantity": 0,
      "cancelled_quantity": 0,
      "market_protection": 0,
      "placed_by": "AB1234",
      "tag": null,
      "meta": {}
    }
  ]
}
```

### Order Response Attributes

| Attribute            | Type   | Description                          |
| -------------------- | ------ | ------------------------------------ |
| `order_id`           | string | Unique order ID                      |
| `exchange_order_id`  | string | Exchange order ID (null if not sent) |
| `parent_order_id`    | string | Parent order ID (for CO)             |
| `status`             | string | Current status                       |
| `status_message`     | string | Human-readable status message        |
| `order_timestamp`    | string | API registration timestamp           |
| `exchange_timestamp` | string | Exchange registration timestamp      |
| `variety`            | string | Order variety                        |
| `modified`           | bool   | If order was modified                |
| `tradingsymbol`      | string | Trading symbol                       |
| `exchange`           | string | Exchange                             |
| `instrument_token`   | int    | Instrument token (for WebSocket)     |
| `transaction_type`   | string | BUY or SELL                          |
| `order_type`         | string | Order type                           |
| `product`            | string | Margin product                       |
| `quantity`           | int    | Total quantity                       |
| `average_price`      | float  | Average execution price              |
| `filled_quantity`    | int    | Executed quantity                    |
| `pending_quantity`   | int    | Remaining quantity                   |
| `cancelled_quantity` | int    | Cancelled quantity                   |
| `tag`                | string | Custom tag                           |

---

## Order Statuses

### Common Statuses

| Status      | Description               |
| ----------- | ------------------------- |
| `OPEN`      | Order is open at exchange |
| `COMPLETE`  | Order fully executed      |
| `CANCELLED` | Order cancelled           |
| `REJECTED`  | Order rejected            |

### Interim Statuses

| Status                      | Description                      |
| --------------------------- | -------------------------------- |
| `PUT ORDER REQ RECEIVED`    | Request received                 |
| `VALIDATION PENDING`        | RMS validation pending           |
| `OPEN PENDING`              | Pending exchange registration    |
| `MODIFY VALIDATION PENDING` | Modification validation pending  |
| `MODIFY PENDING`            | Modification pending at exchange |
| `TRIGGER PENDING`           | SL trigger pending               |
| `CANCEL PENDING`            | Cancellation pending             |
| `AMO REQ RECEIVED`          | AMO request received             |

---

## Order History

Get all status changes for an order:

```bash
curl https://api.kite.trade/orders/220303000308932 \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

Returns array of order states from placement to completion.

---

## Trades

### Get All Trades

```bash
curl https://api.kite.trade/trades \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": [
    {
      "trade_id": "10000000",
      "order_id": "220303000308932",
      "exchange_order_id": "1300000029561105",
      "exchange": "NSE",
      "tradingsymbol": "SBIN",
      "instrument_token": 779521,
      "product": "CNC",
      "transaction_type": "BUY",
      "average_price": 470,
      "quantity": 1,
      "fill_timestamp": "2025-01-17 11:49:45",
      "order_timestamp": "11:49:45",
      "exchange_timestamp": "2025-01-17 11:49:45"
    }
  ]
}
```

### Get Order-Specific Trades

```bash
curl https://api.kite.trade/orders/220303000308932/trades \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

---

## Cover Orders (CO)

Multi-legged orders with built-in stoploss:

```bash
curl https://api.kite.trade/orders/co \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "tradingsymbol=SBIN" \
  -d "exchange=NSE" \
  -d "transaction_type=BUY" \
  -d "order_type=LIMIT" \
  -d "quantity=1" \
  -d "price=750" \
  -d "trigger_price=745" \
  -d "product=MIS" \
  -d "validity=DAY"
```

The second-leg (stoploss) order has `parent_order_id` referencing the first-leg.

---

## Iceberg Orders

Split large orders into smaller legs:

```bash
curl https://api.kite.trade/orders/iceberg \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "tradingsymbol=SBIN" \
  -d "exchange=NSE" \
  -d "transaction_type=BUY" \
  -d "order_type=LIMIT" \
  -d "quantity=1000" \
  -d "price=750" \
  -d "product=CNC" \
  -d "validity=TTL" \
  -d "validity_ttl=5" \
  -d "iceberg_legs=5" \
  -d "iceberg_quantity=200"
```

---

## Tagging Orders

Add custom tags for filtering and identification:

```bash
-d "tag=my_strategy_v1"
```

Tag appears in order response and can be used for tracking.

---

## Python Examples

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Place market order
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="SBIN",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    order_type=kite.ORDER_TYPE_MARKET,
    product=kite.PRODUCT_CNC
)

# Place limit order
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="INFY",
    transaction_type=kite.TRANSACTION_TYPE_BUY,
    quantity=1,
    order_type=kite.ORDER_TYPE_LIMIT,
    price=1500,
    product=kite.PRODUCT_CNC
)

# Modify order
kite.modify_order(
    variety=kite.VARIETY_REGULAR,
    order_id=order_id,
    quantity=2,
    price=1495
)

# Cancel order
kite.cancel_order(
    variety=kite.VARIETY_REGULAR,
    order_id=order_id
)

# Get orders
orders = kite.orders()

# Get trades
trades = kite.trades()
```

---

## Important Notes

1. **Order placement ≠ execution**: Always verify status via order history or postbacks
2. **Use postbacks** for real-time order updates instead of polling
3. **Rate limits apply**: 10 orders/second, 200 orders/minute, 3000 orders/day
4. **Check margins** before placing orders to avoid rejection

---

_Last Updated: December 2025_
