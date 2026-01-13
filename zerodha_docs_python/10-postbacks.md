# Kite Connect API - Postbacks (Webhooks)

## Overview

Postbacks are HTTP POST callbacks sent to your registered URL when order status changes. They provide real-time order updates without polling.

---

## Setup

1. Register a `postback_url` in your app settings on the developer console
2. Ensure your endpoint accepts POST requests with JSON body
3. Implement checksum validation for security

---

## When Postbacks are Sent

| Event       | Description                        |
| ----------- | ---------------------------------- |
| `COMPLETE`  | Order fully executed               |
| `CANCELLED` | Order cancelled                    |
| `REJECTED`  | Order rejected                     |
| `UPDATE`    | Order modified or partially filled |

---

## Payload Structure

Postbacks are sent as raw JSON in the HTTP POST body:

```json
{
  "user_id": "AB1234",
  "unfilled_quantity": 0,
  "app_id": 1234,
  "checksum": "2011845d9348bd6795151bf4258102a03431e3bb12a79c0df73fcb4b7fde4b5d",
  "placed_by": "AB1234",
  "order_id": "220303000308932",
  "exchange_order_id": "1000000001482421",
  "parent_order_id": null,
  "status": "COMPLETE",
  "status_message": null,
  "status_message_raw": null,
  "order_timestamp": "2025-03-03 09:24:25",
  "exchange_update_timestamp": "2025-03-03 09:24:25",
  "exchange_timestamp": "2025-03-03 09:24:25",
  "variety": "regular",
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
  "meta": {},
  "tag": null,
  "guid": "XXXXXX"
}
```

---

## Payload Attributes

| Attribute                   | Type   | Description                           |
| --------------------------- | ------ | ------------------------------------- |
| `order_id`                  | string | Unique order ID                       |
| `exchange_order_id`         | string | Exchange-generated order ID           |
| `parent_order_id`           | string | Parent order (for CO legs)            |
| `placed_by`                 | string | User who placed the order             |
| `app_id`                    | int    | Your Kite Connect app ID              |
| `user_id`                   | string | User ID for whom order was placed     |
| `status`                    | string | COMPLETE, REJECTED, CANCELLED, UPDATE |
| `status_message`            | string | Human-readable status                 |
| `status_message_raw`        | string | Raw status from OMS                   |
| `tradingsymbol`             | string | Trading symbol                        |
| `exchange`                  | string | Exchange                              |
| `instrument_token`          | int    | Instrument token                      |
| `order_type`                | string | MARKET, LIMIT, SL, SL-M               |
| `transaction_type`          | string | BUY or SELL                           |
| `validity`                  | string | DAY, IOC, TTL                         |
| `variety`                   | string | regular, amo, co, etc.                |
| `product`                   | string | CNC, NRML, MIS                        |
| `quantity`                  | int    | Total quantity                        |
| `filled_quantity`           | int    | Executed quantity                     |
| `unfilled_quantity`         | int    | Remaining quantity                    |
| `pending_quantity`          | int    | Pending quantity                      |
| `cancelled_quantity`        | int    | Cancelled quantity                    |
| `disclosed_quantity`        | int    | Disclosed quantity                    |
| `price`                     | float  | Order price                           |
| `trigger_price`             | float  | Trigger price                         |
| `average_price`             | float  | Average execution price               |
| `order_timestamp`           | string | Order registration time               |
| `exchange_timestamp`        | string | Exchange registration time            |
| `exchange_update_timestamp` | string | Last update time                      |
| `checksum`                  | string | Security checksum                     |
| `meta`                      | object | Additional metadata                   |
| `tag`                       | string | Custom order tag                      |

---

## Checksum Validation

**Critical**: Always validate the checksum to ensure the postback is from Kite Connect.

### Checksum Formula

```
checksum = SHA256(order_id + order_timestamp + api_secret)
```

### Python Example

```python
import hashlib
import json

def validate_postback(payload, api_secret):
    """Validate postback checksum"""
    received_checksum = payload.get('checksum')
    order_id = payload.get('order_id')
    order_timestamp = payload.get('order_timestamp')

    # Calculate expected checksum
    data = f"{order_id}{order_timestamp}{api_secret}"
    expected_checksum = hashlib.sha256(data.encode()).hexdigest()

    return received_checksum == expected_checksum
```

---

## Flask Webhook Handler

```python
from flask import Flask, request, jsonify
import hashlib
import json

app = Flask(__name__)
API_SECRET = "your_api_secret"

@app.route('/webhook/kite', methods=['POST'])
def kite_webhook():
    """Handle Kite Connect postbacks"""
    try:
        # Parse JSON payload
        payload = request.get_json()

        # Validate checksum
        if not validate_checksum(payload):
            return jsonify({"error": "Invalid checksum"}), 401

        # Process order update
        order_id = payload['order_id']
        status = payload['status']

        if status == 'COMPLETE':
            handle_order_complete(payload)
        elif status == 'REJECTED':
            handle_order_rejected(payload)
        elif status == 'CANCELLED':
            handle_order_cancelled(payload)
        elif status == 'UPDATE':
            handle_order_update(payload)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def validate_checksum(payload):
    received = payload.get('checksum')
    order_id = payload.get('order_id')
    timestamp = payload.get('order_timestamp')

    expected = hashlib.sha256(
        f"{order_id}{timestamp}{API_SECRET}".encode()
    ).hexdigest()

    return received == expected

def handle_order_complete(payload):
    print(f"Order {payload['order_id']} completed")
    print(f"  Symbol: {payload['tradingsymbol']}")
    print(f"  Qty: {payload['filled_quantity']} @ {payload['average_price']}")
    # Update database, send notifications, etc.

def handle_order_rejected(payload):
    print(f"Order {payload['order_id']} rejected")
    print(f"  Reason: {payload['status_message']}")
    # Alert user, retry logic, etc.

def handle_order_cancelled(payload):
    print(f"Order {payload['order_id']} cancelled")
    # Update tracking, free up resources, etc.

def handle_order_update(payload):
    print(f"Order {payload['order_id']} updated")
    print(f"  Filled: {payload['filled_quantity']}/{payload['quantity']}")
    # Track partial fills, update position, etc.

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## FastAPI Webhook Handler

```python
from fastapi import FastAPI, Request, HTTPException
import hashlib

app = FastAPI()
API_SECRET = "your_api_secret"

@app.post("/webhook/kite")
async def kite_webhook(request: Request):
    payload = await request.json()

    # Validate checksum
    if not validate_checksum(payload):
        raise HTTPException(status_code=401, detail="Invalid checksum")

    status = payload['status']
    order_id = payload['order_id']

    # Process based on status
    if status == 'COMPLETE':
        await process_complete(payload)
    elif status == 'REJECTED':
        await process_rejected(payload)
    elif status == 'UPDATE':
        await process_update(payload)

    return {"status": "ok"}

def validate_checksum(payload):
    received = payload.get('checksum')
    data = f"{payload['order_id']}{payload['order_timestamp']}{API_SECRET}"
    expected = hashlib.sha256(data.encode()).hexdigest()
    return received == expected

async def process_complete(payload):
    # Handle completed order
    pass

async def process_rejected(payload):
    # Handle rejected order
    pass

async def process_update(payload):
    # Handle order update (modification/partial fill)
    pass
```

---

## WebSocket Postbacks

For individual users, postbacks are also delivered via WebSocket:

```python
from kiteconnect import KiteTicker

kws = KiteTicker("api_key", "access_token")

def on_order_update(ws, data):
    """Handle order updates via WebSocket"""
    print(f"Order update: {data['order_id']}")
    print(f"Status: {data['status']}")
    if data['status'] == 'COMPLETE':
        print(f"Executed at {data['average_price']}")

kws.on_order_update = on_order_update
kws.connect()
```

---

## Use Case: Postback vs WebSocket

| Feature             | HTTP Postback            | WebSocket Postback    |
| ------------------- | ------------------------ | --------------------- |
| Scope               | All users of your app    | Single user           |
| Requires connection | No                       | Yes (WebSocket open)  |
| User logged in      | Not required             | Required              |
| Use case            | Platform/multi-user apps | Personal trading apps |

---

## Processing Partial Fills

For large orders that fill partially:

```python
def handle_partial_fill(payload):
    """Track partial fills"""
    order_id = payload['order_id']
    filled = payload['filled_quantity']
    total = payload['quantity']
    pending = payload['pending_quantity']

    # Check if this is a partial fill
    if filled > 0 and pending > 0:
        print(f"Partial fill: {filled}/{total} executed, {pending} pending")

        # Track cumulative fills
        update_order_tracking(order_id, filled)

    elif filled == total:
        print(f"Order fully filled: {filled} @ {payload['average_price']}")
        complete_order_tracking(order_id)
```

---

## Error Handling

```python
def handle_rejected_order(payload):
    """Handle rejected orders"""
    order_id = payload['order_id']
    reason = payload['status_message']
    raw_reason = payload['status_message_raw']

    # Common rejection reasons
    if 'margin' in reason.lower():
        handle_margin_shortage(payload)
    elif 'quantity' in reason.lower():
        handle_quantity_issue(payload)
    elif 'circuit' in reason.lower():
        handle_circuit_limit(payload)
    else:
        log_rejection(order_id, reason, raw_reason)
```

---

## Best Practices

1. **Always validate checksum** - Critical for security
2. **Respond quickly** - Return 200 within seconds
3. **Process async** - Queue heavy processing for background
4. **Handle duplicates** - Same postback may arrive multiple times
5. **Log everything** - Store raw payload for debugging
6. **Retry logic** - If your endpoint is down, postbacks are lost

---

## Webhook Security

1. **HTTPS only** - Use SSL for your webhook URL
2. **Validate checksum** - Never skip this step
3. **IP whitelisting** - If possible, whitelist Kite's IPs
4. **Rate limiting** - Protect against potential DoS
5. **Authentication** - Add additional auth token if needed

---

## Testing Webhooks

For local development, use tools like:

- **ngrok**: `ngrok http 5000`
- **localtunnel**: `lt --port 5000`

Update your app's postback URL to the tunnel URL for testing.

---

_Last Updated: December 2025_
