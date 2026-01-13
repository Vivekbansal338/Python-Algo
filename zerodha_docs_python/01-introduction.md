# Kite Connect API - Introduction & Setup

## Overview

Kite Connect is a set of REST-like HTTP APIs that expose capabilities required to build a complete stock market investment and trading platform. It allows you to:

- Execute orders in real-time (equities, commodities, mutual funds)
- Manage user portfolios
- Stream live market data over WebSockets
- Access historical candle data
- And more...

---

## API Characteristics

| Aspect            | Details                                          |
| ----------------- | ------------------------------------------------ |
| **Input Format**  | Form-encoded parameters                          |
| **Output Format** | JSON (with some exceptions)                      |
| **Compression**   | Responses may be Gzipped                         |
| **Status Codes**  | Standard HTTP codes for success/error            |
| **CORS**          | Not enabled (cannot call from browsers directly) |

---

## Getting Started

### Prerequisites

#### 1. Trading Account Requirements

- Active Zerodha trading account
- Account with 2FA TOTP enabled

#### 2. Developer Account Setup

1. **Create Developer Account**: Visit [Kite Connect Developer Portal](https://kite.trade)
2. **App Creation**: Log in and create a new app to get API credentials
3. **Set Redirect URL**: Configure the URL where users are redirected after authentication
4. **Get API Keys**: Note down your `api_key` and `api_secret` (keep secret secure)

> **Note**: Visit the [Developer Community Forum](https://kite.trade) for support and discussions.

---

## API Version & Endpoint

### Root API Endpoint

```
https://api.kite.trade
```

### Current Version

The current stable version is **3**. Always specify version explicitly for production.

### Requesting a Version

Set the HTTP header:

```
X-Kite-Version: 3
```

---

## Available SDKs

| Language    | Repository                                                          |
| ----------- | ------------------------------------------------------------------- |
| **Python**  | [kiteconnect-python](https://github.com/zerodha/pykiteconnect)      |
| **Go**      | [kiteconnect-go](https://github.com/zerodha/gokiteconnect)          |
| **Java**    | [kiteconnect-java](https://github.com/zerodha/javakiteconnect)      |
| **PHP**     | [kiteconnect-php](https://github.com/zerodha/phpkiteconnect)        |
| **Node.js** | [kiteconnect-nodejs](https://github.com/zerodha/kiteconnect-nodejs) |
| **.NET/C#** | [kiteconnect-dotnet](https://github.com/zerodha/dotnetkiteconnect)  |

---

## Response Structure

### Successful Response

```json
{
  "status": "success",
  "data": {}
}
```

### Failed Response

```json
{
  "status": "error",
  "message": "Error message",
  "error_type": "GeneralException"
}
```

---

## Data Types

| Type          | Format                                |
| ------------- | ------------------------------------- |
| **Timestamp** | `yyyy-mm-dd hh:mm:ss` (IST - UTC+5.5) |
| **Date**      | `yyyy-mm-dd`                          |
| **Values**    | `string`, `int`, `float`, `bool`      |

---

## Exceptions & Error Handling

### Exception Types

| Exception          | Description                                                   |
| ------------------ | ------------------------------------------------------------- |
| `TokenException`   | Session expired/invalidated (403). Clear session and re-login |
| `UserException`    | User account related errors                                   |
| `OrderException`   | Order placement failures, corrupt fetch, etc.                 |
| `InputException`   | Missing required fields, bad parameter values                 |
| `MarginException`  | Insufficient funds for order placement                        |
| `HoldingException` | Insufficient holdings for sell order                          |
| `NetworkException` | API unable to communicate with OMS                            |
| `DataException`    | Internal error parsing OMS response                           |
| `GeneralException` | Unclassified error (rare)                                     |

### HTTP Error Codes

| Code  | Meaning                           |
| ----- | --------------------------------- |
| `400` | Missing or bad request parameters |
| `403` | Session expired or invalid        |
| `404` | Resource not found                |
| `405` | Method not allowed                |
| `410` | Resource permanently gone         |
| `429` | Rate limit exceeded               |
| `500` | Internal server error             |
| `502` | Backend OMS is down               |
| `503` | API service unavailable           |
| `504` | Gateway timeout                   |

---

## API Rate Limits

| Endpoint            | Rate Limit         |
| ------------------- | ------------------ |
| Quote API           | 1 request/second   |
| Historical candle   | 3 requests/second  |
| Order placement     | 10 requests/second |
| All other endpoints | 10 requests/second |

### Additional Limits

- **200 orders per minute**
- **10 orders per second**
- **3000 orders per day** (per user/API key, across all segments)
- **25 modifications per order** (cancel and re-place after limit)

---

## Quick Start Example

```python
import logging
from kiteconnect import KiteConnect

logging.basicConfig(level=logging.DEBUG)

# Initialize client
kite = KiteConnect(api_key="your_api_key")

# Get login URL - redirect user here
print(kite.login_url())

# After login, exchange request_token for access_token
data = kite.generate_session("request_token_here", api_secret="your_secret")
kite.set_access_token(data["access_token"])

# Now you can make API calls
print(kite.profile())
print(kite.orders())
```

---

## Security Best Practices

1. **Never expose `api_secret`** in client-side code or mobile apps
2. **Never expose `access_token`** to public
3. Store tokens securely (encrypted database, environment variables)
4. Use HTTPS for all communications
5. Validate checksums on postbacks/webhooks
6. Implement proper session management

---

## Next Steps

1. Complete Authentication (see [02-authentication.md](02-authentication.md))
2. Choose your SDK
3. Explore the API documentation
4. Start with paper trading before going live

---

_Last Updated: December 2025_
