# Zerodha Kite Connect API Documentation

Welcome to the organized Kite Connect API documentation. This folder contains comprehensive, structured documentation for building trading applications with Zerodha's APIs.

---

## Documentation Index

| #   | Document                                      | Description                                            |
| --- | --------------------------------------------- | ------------------------------------------------------ |
| 01  | [Introduction](01-introduction.md)            | API overview, setup, rate limits, error handling       |
| 02  | [Authentication](02-authentication.md)        | Login flow, token exchange, session management         |
| 03  | [Orders](03-orders.md)                        | Order placement, modification, cancellation, varieties |
| 04  | [GTT & Alerts](04-gtt-alerts.md)              | Good Till Triggered orders and Alerts API              |
| 05  | [Portfolio](05-portfolio.md)                  | Holdings, positions, position conversion               |
| 06  | [Market Data](06-market-data.md)              | Instruments master, quotes, market depth               |
| 07  | [WebSocket](07-websocket.md)                  | Real-time streaming, binary protocol                   |
| 08  | [Historical Data](08-historical-data.md)      | OHLCV candle data, intervals                           |
| 09  | [Margins & Charges](09-margins-charges.md)    | Margin calculation, trading charges                    |
| 10  | [Postbacks](10-postbacks.md)                  | Webhooks for order updates                             |
| 11  | [Python SDK](11-python-sdk.md)                | Complete SDK reference                                 |
| 12  | [Intraday Brokerage](12-intraday-brokrage.md) | Brokerage charges for intraday equity trading          |

---

## Quick Links

### API Endpoints

- **REST API**: `https://api.kite.trade`
- **WebSocket**: `wss://ws.kite.trade`
- **Login**: `https://kite.zerodha.com/connect/login`

### Rate Limits

| Type                    | Limit            |
| ----------------------- | ---------------- |
| API Requests            | 10/second        |
| Order Requests          | 10/second        |
| Historical Data         | 3/second         |
| WebSocket Connections   | 3 per user       |
| WebSocket Subscriptions | 3000 instruments |

---

## Getting Started

### 1. Install SDK

```bash
pip install kiteconnect
```

### 2. Authentication Flow

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_api_key")

# Get login URL
print(kite.login_url())

# After user login, exchange request_token
data = kite.generate_session("request_token", api_secret="your_secret")
kite.set_access_token(data["access_token"])
```

### 3. Place Your First Order

```python
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
```

### 4. Stream Live Data

```python
from kiteconnect import KiteTicker

kws = KiteTicker("api_key", "access_token")

def on_ticks(ws, ticks):
    print(ticks)

def on_connect(ws, response):
    ws.subscribe([779521])  # SBIN

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.connect()
```

---

## Response Structure

All API responses follow this structure:

### Success

```json
{
  "status": "success",
  "data": { ... }
}
```

### Error

```json
{
  "status": "error",
  "message": "Error description",
  "error_type": "ErrorType"
}
```

---

## Common Error Types

| Error Type         | HTTP Code | Description                         |
| ------------------ | --------- | ----------------------------------- |
| `TokenException`   | 403       | Invalid or expired token            |
| `InputException`   | 400       | Invalid input parameters            |
| `OrderException`   | 400       | Order placement/modification failed |
| `DataException`    | 502       | Data source error                   |
| `GeneralException` | 500       | General server error                |
| `NetworkException` | 503       | Network connectivity issues         |

---

## Supported Exchanges

| Exchange   | Code    | Products  |
| ---------- | ------- | --------- |
| NSE Equity | NSE     | CNC, MIS  |
| BSE Equity | BSE     | CNC, MIS  |
| NSE F&O    | NFO     | NRML, MIS |
| Currency   | CDS/BCD | NRML, MIS |
| Commodity  | MCX     | NRML, MIS |

---

## Important Notes

1. **Rate Limiting**: Respect rate limits to avoid being blocked
2. **Token Expiry**: Access tokens expire at 7:30 AM daily
3. **Market Hours**: Trading APIs work only during market hours
4. **Instrument Updates**: Refresh instruments daily (expiry changes)
5. **Testing**: Use small quantities for testing

---

## Resources

- [Official Kite Connect Docs](https://kite.trade/docs/connect/v3/)
- [Developer Forum](https://kite.trade/forum)
- [API Status](https://status.zerodha.com/)

---

_Documentation Version: 3.0 | Last Updated: December 2025_
