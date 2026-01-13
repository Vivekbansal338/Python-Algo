# Kite Connect API - Authentication & User Management

## Overview

Authentication in Kite Connect follows OAuth-style flow where users authorize your app to access their trading account. This document covers the complete authentication lifecycle.

---

## Authentication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Redirect user to Kite login URL                             │
│     ↓                                                           │
│  2. User logs in on Zerodha portal                              │
│     ↓                                                           │
│  3. User is redirected to your app with request_token           │
│     ↓                                                           │
│  4. Exchange request_token for access_token via API             │
│     ↓                                                           │
│  5. Use access_token for all subsequent API calls               │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

| Method   | Endpoint                 | Description                             |
| -------- | ------------------------ | --------------------------------------- |
| `POST`   | `/session/token`         | Exchange request_token for access_token |
| `GET`    | `/user/profile`          | Get user profile details                |
| `GET`    | `/user/margins`          | Get funds and margin details            |
| `GET`    | `/user/margins/:segment` | Get segment-specific margins            |
| `DELETE` | `/session/token`         | Logout and invalidate session           |

---

## Step 1: Login URL

Redirect users to this URL to initiate login:

```
https://kite.zerodha.com/connect/login?v=3&api_key=YOUR_API_KEY
```

### Optional Parameters

| Parameter         | Description                                        |
| ----------------- | -------------------------------------------------- |
| `redirect_params` | URL-encoded query params sent back to redirect URL |

**Example with redirect params:**

```
https://kite.zerodha.com/connect/login?v=3&api_key=xxx&redirect_params=some%3DX%26more%3DY
```

---

## Step 2: Token Exchange

After successful login, user is redirected to your registered URL with `request_token`:

```
https://your-redirect-url.com?request_token=XXXXX&action=login&status=success
```

Exchange this token for `access_token`:

### Request

```bash
curl https://api.kite.trade/session/token \
  -H "X-Kite-Version: 3" \
  -d "api_key=YOUR_API_KEY" \
  -d "request_token=RECEIVED_REQUEST_TOKEN" \
  -d "checksum=SHA256_HASH"
```

### Checksum Calculation

```python
import hashlib

checksum = hashlib.sha256(
    (api_key + request_token + api_secret).encode()
).hexdigest()
```

### Response

```json
{
  "status": "success",
  "data": {
    "user_id": "AB1234",
    "user_name": "John Doe",
    "user_shortname": "John",
    "email": "john@example.com",
    "user_type": "individual",
    "broker": "ZERODHA",
    "exchanges": ["NSE", "NFO", "BSE", "MCX", "CDS", "BFO", "MF"],
    "products": ["CNC", "NRML", "MIS", "BO", "CO"],
    "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
    "api_key": "your_api_key",
    "access_token": "ACCESS_TOKEN_HERE",
    "public_token": "PUBLIC_TOKEN_HERE",
    "refresh_token": "",
    "login_time": "2025-12-26 09:15:00",
    "meta": {
      "demat_consent": "physical"
    },
    "avatar_url": null
  }
}
```

### Response Attributes

| Attribute        | Type     | Description                                             |
| ---------------- | -------- | ------------------------------------------------------- |
| `user_id`        | string   | Unique permanent user ID                                |
| `user_name`      | string   | User's real name                                        |
| `user_shortname` | string   | Shortened name                                          |
| `email`          | string   | User's email                                            |
| `user_type`      | string   | Role (always "individual" for retail)                   |
| `broker`         | string   | Broker ID (ZERODHA)                                     |
| `exchanges`      | string[] | Enabled exchanges                                       |
| `products`       | string[] | Enabled margin products                                 |
| `order_types`    | string[] | Enabled order types                                     |
| `access_token`   | string   | Token for API requests (expires at 6 AM next day)       |
| `public_token`   | string   | Token for public session validation                     |
| `refresh_token`  | string   | For long-standing permissions (approved platforms only) |
| `login_time`     | string   | Last login timestamp                                    |

---

## Step 3: Signing Requests

All authenticated requests must include the Authorization header:

```
Authorization: token api_key:access_token
```

### Example

```bash
curl https://api.kite.trade/user/profile \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token YOUR_API_KEY:YOUR_ACCESS_TOKEN"
```

---

## User Profile

Retrieve user profile at any time:

```bash
curl https://api.kite.trade/user/profile \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Response

```json
{
  "status": "success",
  "data": {
    "user_id": "AB1234",
    "user_type": "individual",
    "email": "john@example.com",
    "user_name": "John Doe",
    "user_shortname": "John",
    "broker": "ZERODHA",
    "exchanges": ["NSE", "NFO", "BSE", "MCX", "CDS", "BFO", "MF"],
    "products": ["CNC", "NRML", "MIS", "BO", "CO"],
    "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
    "avatar_url": null,
    "meta": {
      "demat_consent": "physical"
    }
  }
}
```

---

## Funds & Margins

### Get All Margins

```bash
curl https://api.kite.trade/user/margins \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

### Get Segment-Specific Margins

```bash
curl https://api.kite.trade/user/margins/equity \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token"
```

Segments: `equity` or `commodity`

### Response Structure

```json
{
  "status": "success",
  "data": {
    "equity": {
      "enabled": true,
      "net": 99725.05,
      "available": {
        "adhoc_margin": 0,
        "cash": 245431.6,
        "opening_balance": 245431.6,
        "live_balance": 99725.05,
        "collateral": 0,
        "intraday_payin": 0
      },
      "utilised": {
        "debits": 145706.55,
        "exposure": 38981.25,
        "m2m_realised": 761.7,
        "m2m_unrealised": 0,
        "option_premium": 0,
        "payout": 0,
        "span": 101989,
        "holding_sales": 0,
        "turnover": 0,
        "liquid_collateral": 0,
        "stock_collateral": 0,
        "delivery": 0
      }
    },
    "commodity": {
      "enabled": true,
      "net": 100661.7,
      "available": {...},
      "utilised": {...}
    }
  }
}
```

### Margin Response Attributes

| Attribute         | Type  | Description                           |
| ----------------- | ----- | ------------------------------------- |
| `enabled`         | bool  | Segment enabled for user              |
| `net`             | float | Net cash balance available            |
| **Available**     |       |                                       |
| `cash`            | float | Raw cash balance                      |
| `opening_balance` | float | Day start balance                     |
| `live_balance`    | float | Current available balance             |
| `intraday_payin`  | float | Amount deposited today                |
| `adhoc_margin`    | float | Additional margin from broker         |
| `collateral`      | float | Margin from pledged stocks            |
| **Utilised**      |       |                                       |
| `debits`          | float | Sum of all utilised margins           |
| `span`            | float | SPAN margin for F&O                   |
| `exposure`        | float | Exposure margin for F&O               |
| `option_premium`  | float | Options premium received              |
| `m2m_realised`    | float | Booked intraday P&L                   |
| `m2m_unrealised`  | float | Open intraday P&L                     |
| `holding_sales`   | float | Holdings sold today                   |
| `delivery`        | float | Margin blocked on holdings sale (20%) |

---

## Logout

Invalidate session and access_token:

```bash
curl -X DELETE \
  "https://api.kite.trade/session/token?api_key=xxx&access_token=yyy" \
  -H "X-Kite-Version: 3"
```

### Response

```json
{
  "status": "success",
  "data": true
}
```

> **Note**: This does not log user out of Kite web/mobile apps.

---

## Token Renewal

For approved platforms with `refresh_token`:

```python
data = kite.renew_access_token(refresh_token, api_secret)
```

---

## Session Expiry Handling

Set a callback for session errors:

```python
def handle_session_expiry():
    # Clear session, redirect to login
    pass

kite.set_session_expiry_hook(handle_session_expiry)
```

---

## Web Application Flow

For typical web apps:

1. Initialize Kite client instance
2. Redirect user to `login_url()`
3. At redirect URL, extract `request_token` from query params
4. Initialize new Kite client, call `generate_session()`
5. Store `access_token` in session/database
6. Use stored token for all subsequent API calls

---

## Security Reminders

⚠️ **Never expose `api_secret`** in client-side code  
⚠️ **Never embed secrets** in mobile apps  
⚠️ **Access tokens expire at 6 AM** daily  
⚠️ **Validate checksums** on all postbacks

---

_Last Updated: December 2025_
