# Kite Connect API - GTT Orders & Alerts

## Overview

GTT (Good Till Triggered) orders and Alerts allow you to set up conditional triggers that execute when market conditions are met. GTT orders automatically place trades, while Alerts provide notifications.

---

## Part 1: GTT Orders

### API Endpoints

| Method   | Endpoint            | Description         |
| -------- | ------------------- | ------------------- |
| `POST`   | `/gtt/triggers`     | Create a GTT order  |
| `GET`    | `/gtt/triggers`     | List all GTT orders |
| `GET`    | `/gtt/triggers/:id` | Get specific GTT    |
| `PUT`    | `/gtt/triggers/:id` | Modify a GTT        |
| `DELETE` | `/gtt/triggers/:id` | Delete a GTT        |

---

### GTT Types

| Type      | Description                                                   |
| --------- | ------------------------------------------------------------- |
| `single`  | Single trigger - executes one order when price is reached     |
| `two-leg` | OCO (One Cancels Other) - two triggers, one cancels the other |

---

### Creating a Single GTT

```bash
curl https://api.kite.trade/gtt/triggers \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d 'type=single' \
  -d 'condition={"exchange":"NSE", "tradingsymbol":"INFY", "trigger_values":[702.0], "last_price": 798.0}' \
  -d 'orders=[{"exchange":"NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": 1, "order_type": "LIMIT","product": "CNC", "price": 702.5}]'
```

#### Response

```json
{
  "status": "success",
  "data": {
    "trigger_id": 123
  }
}
```

---

### Creating a Two-Leg GTT (OCO)

```bash
curl https://api.kite.trade/gtt/triggers \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d 'type=two-leg' \
  -d 'condition={"exchange":"NSE", "tradingsymbol":"INFY", "trigger_values":[702.0, 798.0], "last_price": 742.0}' \
  -d 'orders=[
    {"exchange":"NSE", "tradingsymbol": "INFY", "transaction_type": "SELL", "quantity": 1, "order_type": "LIMIT","product": "CNC", "price": 702.5},
    {"exchange":"NSE", "tradingsymbol": "INFY", "transaction_type": "SELL", "quantity": 1, "order_type": "LIMIT","product": "CNC", "price": 798.5}
  ]'
```

---

### GTT Parameters

#### Order Parameters

| Parameter   | Description                   |
| ----------- | ----------------------------- |
| `type`      | GTT type (single/two-leg)     |
| `condition` | Condition object (JSON)       |
| `orders`    | Array of order objects (JSON) |

#### Condition Object

| Field            | Description                     |
| ---------------- | ------------------------------- |
| `exchange`       | Exchange name                   |
| `tradingsymbol`  | Trading symbol                  |
| `trigger_values` | Array of trigger prices         |
| `last_price`     | Current/last price at placement |

#### Order Object

| Field              | Description    |
| ------------------ | -------------- |
| `exchange`         | Exchange name  |
| `tradingsymbol`    | Trading symbol |
| `transaction_type` | BUY or SELL    |
| `quantity`         | Order quantity |
| `order_type`       | LIMIT only     |
| `product`          | CNC, NRML, MIS |
| `price`            | Limit price    |

---

### Retrieving GTT Orders

#### List All GTTs

```bash
curl https://api.kite.trade/gtt/triggers \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Response

```json
{
  "status": "success",
  "data": [
    {
      "id": 112127,
      "user_id": "AB1234",
      "parent_trigger": null,
      "type": "single",
      "created_at": "2025-09-12 13:25:16",
      "updated_at": "2025-09-12 13:25:16",
      "expires_at": "2026-09-12 13:25:16",
      "status": "active",
      "condition": {
        "exchange": "NSE",
        "last_price": 798,
        "tradingsymbol": "INFY",
        "trigger_values": [702],
        "instrument_token": 408065
      },
      "orders": [
        {
          "exchange": "NSE",
          "tradingsymbol": "INFY",
          "product": "CNC",
          "order_type": "LIMIT",
          "transaction_type": "BUY",
          "quantity": 1,
          "price": 702.5,
          "result": null
        }
      ],
      "meta": {}
    }
  ]
}
```

---

### GTT Statuses

| Status      | Description                            |
| ----------- | -------------------------------------- |
| `active`    | Trigger is active and monitoring       |
| `triggered` | Trigger was executed                   |
| `disabled`  | Trigger disabled, user action required |
| `expired`   | Trigger expired (default: 1 year)      |
| `cancelled` | Cancelled by system                    |
| `rejected`  | Rejected by system                     |
| `deleted`   | Deleted by user                        |

---

### Modifying GTT

```bash
curl -X PUT https://api.kite.trade/gtt/triggers/123 \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d 'type=single' \
  -d 'condition={"exchange":"NSE", "tradingsymbol":"INFY", "trigger_values":[701.0], "last_price": 798.0}' \
  -d 'orders=[{"exchange":"NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "quantity": 1, "order_type": "LIMIT","product": "CNC", "price": 702.5}]'
```

> **Tip**: Fetch trigger first, modify values, then send update.

---

### Deleting GTT

```bash
curl -X DELETE https://api.kite.trade/gtt/triggers/123 \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

---

## Part 2: Alerts

Alerts notify you when price conditions are met. ATO (Alert Triggers Order) alerts can also place orders automatically.

### API Endpoints

| Method   | Endpoint                | Description        |
| -------- | ----------------------- | ------------------ |
| `POST`   | `/alerts`               | Create an alert    |
| `GET`    | `/alerts`               | List all alerts    |
| `GET`    | `/alerts/:uuid`         | Get specific alert |
| `PUT`    | `/alerts/:uuid`         | Modify an alert    |
| `DELETE` | `/alerts?uuid=:uuid`    | Delete alert(s)    |
| `GET`    | `/alerts/:uuid/history` | Get alert history  |

---

### Alert Types

| Type     | Description                                        |
| -------- | -------------------------------------------------- |
| `simple` | Standard price notification                        |
| `ato`    | Alert Triggers Order - places order when triggered |

---

### Creating a Simple Alert

```bash
curl https://api.kite.trade/alerts \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "name=NIFTY 50 Alert" \
  -d "lhs_exchange=INDICES" \
  -d "lhs_tradingsymbol=NIFTY 50" \
  -d "lhs_attribute=LastTradedPrice" \
  -d "operator=>=" \
  -d "rhs_type=constant" \
  -d "type=simple" \
  -d "rhs_constant=27000"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "type": "simple",
    "user_id": "AB1234",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "name": "NIFTY 50 Alert",
    "status": "enabled",
    "lhs_attribute": "LastTradedPrice",
    "lhs_exchange": "INDICES",
    "lhs_tradingsymbol": "NIFTY 50",
    "operator": ">=",
    "rhs_type": "constant",
    "rhs_constant": 27000,
    "alert_count": 0,
    "created_at": "2025-12-26 12:07:50",
    "updated_at": "2025-12-26 12:07:50"
  }
}
```

---

### Creating an ATO Alert

```bash
curl https://api.kite.trade/alerts \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "name=Buy RELIANCE" \
  -d "lhs_exchange=NSE" \
  -d "lhs_tradingsymbol=RELIANCE" \
  -d "lhs_attribute=LastTradedPrice" \
  -d "operator=<=" \
  -d "rhs_type=constant" \
  -d "type=ato" \
  -d "rhs_constant=2500" \
  -d 'basket={"name":"alerts-basket","type":"alert","tags":[],"items":[{"type":"insert","tradingsymbol":"RELIANCE","exchange":"NSE","weight":10000,"params":{"transaction_type":"BUY","product":"CNC","order_type":"MARKET","validity":"DAY","quantity":1,"price":0,"trigger_price":0,"variety":"regular"}}]}'
```

---

### Alert Parameters

| Parameter           | Description                                       |
| ------------------- | ------------------------------------------------- |
| `name`              | Alert name                                        |
| `type`              | simple or ato                                     |
| `lhs_exchange`      | Left-hand side exchange                           |
| `lhs_tradingsymbol` | Left-hand side symbol                             |
| `lhs_attribute`     | Attribute to monitor (e.g., LastTradedPrice)      |
| `operator`          | Comparison operator                               |
| `rhs_type`          | constant or instrument                            |
| `rhs_constant`      | Value to compare (if rhs_type=constant)           |
| `rhs_exchange`      | Right-hand side exchange (if rhs_type=instrument) |
| `rhs_tradingsymbol` | Right-hand side symbol (if rhs_type=instrument)   |
| `basket`            | Order basket JSON (for ATO alerts)                |

---

### Operators

| Operator | Description           |
| -------- | --------------------- |
| `<=`     | Less than or equal    |
| `>=`     | Greater than or equal |
| `<`      | Less than             |
| `>`      | Greater than          |
| `==`     | Equal to              |

---

### ATO Basket Structure

```json
{
  "name": "alerts-basket",
  "type": "alert",
  "tags": [],
  "items": [
    {
      "type": "insert",
      "tradingsymbol": "RELIANCE",
      "exchange": "NSE",
      "weight": 10000,
      "params": {
        "transaction_type": "BUY",
        "product": "CNC",
        "order_type": "MARKET",
        "validity": "DAY",
        "quantity": 1,
        "price": 0,
        "trigger_price": 0,
        "variety": "regular"
      }
    }
  ]
}
```

---

### Alert Statuses

| Status     | Description       |
| ---------- | ----------------- |
| `enabled`  | Alert is active   |
| `disabled` | Alert is disabled |
| `deleted`  | Alert was deleted |

---

### Retrieving Alerts

```bash
curl "https://api.kite.trade/alerts" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Query Parameters

| Parameter   | Description      |
| ----------- | ---------------- |
| `status`    | Filter by status |
| `page`      | Page number      |
| `page_size` | Alerts per page  |

---

### Modifying Alerts

```bash
curl -X PUT "https://api.kite.trade/alerts/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -d "rhs_constant=27500"
```

---

### Deleting Alerts

#### Single Alert

```bash
curl -X DELETE "https://api.kite.trade/alerts?uuid=550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

#### Multiple Alerts

```bash
curl -X DELETE "https://api.kite.trade/alerts?uuid=UUID1&uuid=UUID2" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

---

### Alert History

```bash
curl "https://api.kite.trade/alerts/550e8400-e29b-41d4-a716-446655440000/history" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

Returns trigger history with market data at trigger time.

---

## Python Examples

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Create GTT - Single Leg
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="INFY",
    exchange="NSE",
    trigger_values=[700],
    last_price=750,
    orders=[{
        "exchange": "NSE",
        "tradingsymbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 1,
        "order_type": "LIMIT",
        "product": "CNC",
        "price": 700.5
    }]
)

# Create GTT - Two Leg (OCO)
gtt_id = kite.place_gtt(
    trigger_type=kite.GTT_TYPE_OCO,
    tradingsymbol="INFY",
    exchange="NSE",
    trigger_values=[680, 780],
    last_price=750,
    orders=[
        {"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "SELL",
         "quantity": 1, "order_type": "LIMIT", "product": "CNC", "price": 680},
        {"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "SELL",
         "quantity": 1, "order_type": "LIMIT", "product": "CNC", "price": 780}
    ]
)

# Get all GTTs
gtts = kite.get_gtts()

# Get specific GTT
gtt = kite.get_gtt(trigger_id=gtt_id)

# Modify GTT
kite.modify_gtt(
    trigger_id=gtt_id,
    trigger_type=kite.GTT_TYPE_SINGLE,
    tradingsymbol="INFY",
    exchange="NSE",
    trigger_values=[695],
    last_price=750,
    orders=[...]
)

# Delete GTT
kite.delete_gtt(trigger_id=gtt_id)
```

---

## Use Cases

### 1. Buy on Dip (Single GTT)

- Set trigger below current price
- Buy order executes when price drops

### 2. Stoploss + Target (Two-Leg GTT)

- Lower trigger: Stoploss sell
- Upper trigger: Target sell
- First triggered executes, other cancels

### 3. Price Alert (Simple Alert)

- Get notified when index/stock crosses level
- No order execution, just notification

### 4. Automated Entry (ATO Alert)

- Monitor price condition
- Automatically place order when condition met

---

_Last Updated: December 2025_
