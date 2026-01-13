# Kite Connect API - Margins & Charges

## Overview

The Margin Calculation APIs help you calculate required margins, spread benefits, and trading charges before placing orders.

---

## API Endpoints

| Method | Endpoint          | Description                                          |
| ------ | ----------------- | ---------------------------------------------------- |
| `POST` | `/margins/orders` | Calculate margins for orders                         |
| `POST` | `/margins/basket` | Calculate basket margins with spread benefit         |
| `POST` | `/charges/orders` | Calculate charges for orders (virtual contract note) |

> **Note**: These endpoints require `Content-Type: application/json` header.

---

## Part 1: Order Margins

Calculate margin requirements for individual orders.

### Request

```bash
curl https://api.kite.trade/margins/orders \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "exchange": "NSE",
      "tradingsymbol": "INFY",
      "transaction_type": "BUY",
      "variety": "regular",
      "product": "CNC",
      "order_type": "MARKET",
      "quantity": 1,
      "price": 0,
      "trigger_price": 0
    }
  ]'
```

### Query Parameters

| Parameter | Description                           |
| --------- | ------------------------------------- |
| `mode`    | `compact` - Only return total margins |

### Response

```json
{
  "status": "success",
  "data": [
    {
      "type": "equity",
      "tradingsymbol": "INFY",
      "exchange": "NSE",
      "span": 0,
      "exposure": 0,
      "option_premium": 0,
      "additional": 0,
      "bo": 0,
      "cash": 0,
      "var": 1498,
      "pnl": {
        "realised": 0,
        "unrealised": 0
      },
      "leverage": 1,
      "charges": {
        "transaction_tax": 1.498,
        "transaction_tax_type": "stt",
        "exchange_turnover_charge": 0.051681,
        "sebi_turnover_charge": 0.001498,
        "brokerage": 0.01,
        "stamp_duty": 0.22,
        "gst": {
          "igst": 0.0114,
          "cgst": 0,
          "sgst": 0,
          "total": 0.0114
        },
        "total": 1.79
      },
      "total": 1498
    }
  ]
}
```

### Order Structure

| Field              | Type   | Description                |
| ------------------ | ------ | -------------------------- |
| `exchange`         | string | Exchange name              |
| `tradingsymbol`    | string | Trading symbol             |
| `transaction_type` | string | BUY or SELL                |
| `variety`          | string | regular, amo, co, etc.     |
| `product`          | string | CNC, NRML, MIS             |
| `order_type`       | string | MARKET, LIMIT, SL, SL-M    |
| `quantity`         | int    | Order quantity             |
| `price`            | float  | Limit price (0 for MARKET) |
| `trigger_price`    | float  | SL trigger price           |

### Margin Response Fields

| Field            | Description           |
| ---------------- | --------------------- |
| `type`           | equity or commodity   |
| `tradingsymbol`  | Trading symbol        |
| `exchange`       | Exchange              |
| `span`           | SPAN margin (F&O)     |
| `exposure`       | Exposure margin (F&O) |
| `option_premium` | Premium for options   |
| `additional`     | Additional margins    |
| `bo`             | Bracket order margin  |
| `cash`           | Cash credit           |
| `var`            | Value at Risk margin  |
| `leverage`       | Margin leverage       |
| `total`          | Total margin required |

---

## Part 2: Basket Margins

Calculate margins for basket orders with spread benefit calculation.

### Request

```bash
curl "https://api.kite.trade/margins/basket?consider_positions=true" \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "exchange": "NFO",
      "tradingsymbol": "NIFTY25JAN20600CE",
      "transaction_type": "SELL",
      "variety": "regular",
      "product": "NRML",
      "order_type": "MARKET",
      "quantity": 75,
      "price": 0,
      "trigger_price": 0
    },
    {
      "exchange": "NFO",
      "tradingsymbol": "NIFTY25JAN20700CE",
      "transaction_type": "BUY",
      "variety": "regular",
      "product": "NRML",
      "order_type": "MARKET",
      "quantity": 75,
      "price": 0,
      "trigger_price": 0
    }
  ]'
```

### Query Parameters

| Parameter            | Description                               |
| -------------------- | ----------------------------------------- |
| `consider_positions` | Include existing positions in calculation |
| `mode`               | `compact` - Only return totals            |

### Response

```json
{
  "status": "success",
  "data": {
    "initial": {
      "type": "",
      "tradingsymbol": "",
      "exchange": "",
      "span": 66832.5,
      "exposure": 29151.22,
      "option_premium": 521.25,
      "additional": 0,
      "bo": 0,
      "cash": 0,
      "var": 0,
      "total": 96504.97
    },
    "final": {
      "type": "",
      "tradingsymbol": "",
      "exchange": "",
      "span": 7788.00,
      "exposure": 29151.22,
      "option_premium": -2152.5,
      "additional": 0,
      "bo": 0,
      "cash": 0,
      "var": 0,
      "total": 34786.72
    },
    "orders": [
      {
        "type": "equity",
        "tradingsymbol": "NIFTY25JAN20600CE",
        "exchange": "NFO",
        "span": 66832.5,
        "exposure": 29151.22,
        "total": 95983.72,
        "charges": {...}
      },
      {
        "type": "equity",
        "tradingsymbol": "NIFTY25JAN20700CE",
        "exchange": "NFO",
        "span": 0,
        "exposure": 0,
        "option_premium": 521.25,
        "total": 521.25,
        "charges": {...}
      }
    ]
  }
}
```

### Response Structure

| Field     | Description                          |
| --------- | ------------------------------------ |
| `initial` | Total margins without spread benefit |
| `final`   | Total margins with spread benefit    |
| `orders`  | Individual order margins             |

### Spread Benefit Calculation

```
Spread Benefit = initial.total - final.total
               = 96504.97 - 34786.72
               = 61718.25 (64% savings!)
```

---

## Part 3: Virtual Contract Note (Charges)

Calculate detailed charges for orders.

### Request

```bash
curl https://api.kite.trade/charges/orders \
  -H "X-Kite-Version: 3" \
  -H "Authorization: token api_key:access_token" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "order_id": "order1",
      "exchange": "NSE",
      "tradingsymbol": "SBIN",
      "transaction_type": "BUY",
      "variety": "regular",
      "product": "CNC",
      "order_type": "MARKET",
      "quantity": 100,
      "average_price": 760
    },
    {
      "order_id": "order2",
      "exchange": "NFO",
      "tradingsymbol": "NIFTY25JAN20000CE",
      "transaction_type": "BUY",
      "variety": "regular",
      "product": "NRML",
      "order_type": "LIMIT",
      "quantity": 75,
      "average_price": 150
    }
  ]'
```

### Response

```json
{
  "status": "success",
  "data": [
    {
      "transaction_type": "BUY",
      "tradingsymbol": "SBIN",
      "exchange": "NSE",
      "variety": "regular",
      "product": "CNC",
      "order_type": "MARKET",
      "quantity": 100,
      "price": 760,
      "charges": {
        "transaction_tax": 76.0,
        "transaction_tax_type": "stt",
        "exchange_turnover_charge": 2.55,
        "sebi_turnover_charge": 0.076,
        "brokerage": 0,
        "stamp_duty": 11.4,
        "gst": {
          "igst": 0.459,
          "cgst": 0,
          "sgst": 0,
          "total": 0.459
        },
        "total": 90.485
      }
    },
    {
      "transaction_type": "BUY",
      "tradingsymbol": "NIFTY25JAN20000CE",
      "exchange": "NFO",
      "variety": "regular",
      "product": "NRML",
      "order_type": "LIMIT",
      "quantity": 75,
      "price": 150,
      "charges": {
        "transaction_tax": 0,
        "transaction_tax_type": "stt",
        "exchange_turnover_charge": 5.66,
        "sebi_turnover_charge": 0.011,
        "brokerage": 20,
        "stamp_duty": 1.69,
        "gst": {
          "igst": 4.62,
          "cgst": 0,
          "sgst": 0,
          "total": 4.62
        },
        "total": 31.98
      }
    }
  ]
}
```

### Charges Breakdown

| Field                      | Description      |
| -------------------------- | ---------------- |
| `transaction_tax`          | STT/CTT          |
| `transaction_tax_type`     | `stt` or `ctt`   |
| `exchange_turnover_charge` | Exchange fee     |
| `sebi_turnover_charge`     | SEBI fee         |
| `brokerage`                | Brokerage charge |
| `stamp_duty`               | Stamp duty       |
| `gst.igst`                 | Integrated GST   |
| `gst.cgst`                 | Central GST      |
| `gst.sgst`                 | State GST        |
| `gst.total`                | Total GST        |
| `total`                    | Total charges    |

---

## Charge Types by Segment

### Equity Delivery (CNC)

| Charge     | Rate               |
| ---------- | ------------------ |
| STT        | 0.1% on buy & sell |
| Exchange   | 0.00345%           |
| SEBI       | 0.0001%            |
| Brokerage  | Zero (Zerodha)     |
| Stamp Duty | 0.015% (buy)       |
| GST        | 18% on brokerage   |

### Equity Intraday (MIS)

| Charge     | Rate             |
| ---------- | ---------------- |
| STT        | 0.025% on sell   |
| Exchange   | 0.00345%         |
| SEBI       | 0.0001%          |
| Brokerage  | ₹20 or 0.03%     |
| Stamp Duty | 0.003% (buy)     |
| GST        | 18% on brokerage |

### F&O

| Charge     | Rate                                            |
| ---------- | ----------------------------------------------- |
| STT        | 0.0125% (sell) for Futures, 0.0625% for Options |
| Exchange   | 0.05%                                           |
| SEBI       | 0.0001%                                         |
| Brokerage  | ₹20 per order                                   |
| Stamp Duty | 0.003% (buy)                                    |
| GST        | 18% on brokerage                                |

### Commodity (MCX)

| Charge     | Rate                      |
| ---------- | ------------------------- |
| CTT        | 0.01% (sell) for non-agri |
| Exchange   | 0.0026%                   |
| SEBI       | 0.0001%                   |
| Brokerage  | ₹20 or 0.03%              |
| Stamp Duty | 0.003% (buy)              |
| GST        | 18% on brokerage          |

---

## Python Examples

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Calculate order margins
margins = kite.order_margins([
    {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25JAN24000CE",
        "transaction_type": "BUY",
        "variety": "regular",
        "product": "NRML",
        "order_type": "MARKET",
        "quantity": 75,
        "price": 0,
        "trigger_price": 0
    }
])

for m in margins:
    print(f"Symbol: {m['tradingsymbol']}")
    print(f"Total Margin: ₹{m['total']:.2f}")
    print(f"SPAN: ₹{m['span']:.2f}")
    print(f"Exposure: ₹{m['exposure']:.2f}")
    print(f"Charges: ₹{m['charges']['total']:.2f}")

# Calculate basket margins
basket_margins = kite.basket_order_margins([
    {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25JAN24000CE",
        "transaction_type": "SELL",
        "variety": "regular",
        "product": "NRML",
        "order_type": "MARKET",
        "quantity": 75,
        "price": 0,
        "trigger_price": 0
    },
    {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY25JAN24100CE",
        "transaction_type": "BUY",
        "variety": "regular",
        "product": "NRML",
        "order_type": "MARKET",
        "quantity": 75,
        "price": 0,
        "trigger_price": 0
    }
], consider_positions=True)

print(f"Initial Margin: ₹{basket_margins['initial']['total']:.2f}")
print(f"Final Margin: ₹{basket_margins['final']['total']:.2f}")
print(f"Spread Benefit: ₹{basket_margins['initial']['total'] - basket_margins['final']['total']:.2f}")
```

---

## Use Cases

### 1. Pre-Order Validation

```python
def check_margin_available(order):
    """Check if sufficient margin before placing order"""
    margins = kite.order_margins([order])
    required = margins[0]['total']

    user_margins = kite.margins()
    available = user_margins['equity']['net']

    if available >= required:
        return True, required, available
    else:
        return False, required, available
```

### 2. Spread Strategy Cost Analysis

```python
def analyze_spread_cost(leg1, leg2):
    """Analyze margin benefit of spread vs naked positions"""

    # Individual margins
    individual = kite.order_margins([leg1, leg2])
    total_individual = sum(m['total'] for m in individual)

    # Basket margins
    basket = kite.basket_order_margins([leg1, leg2])
    total_basket = basket['final']['total']

    benefit = total_individual - total_basket
    benefit_pct = (benefit / total_individual) * 100

    return {
        'individual_margin': total_individual,
        'basket_margin': total_basket,
        'benefit': benefit,
        'benefit_percent': benefit_pct
    }
```

### 3. Calculate Net P&L After Charges

```python
def calculate_net_pnl(buy_price, sell_price, quantity, symbol, exchange):
    """Calculate net P&L after all charges"""

    buy_charges = kite.order_charges([{
        "order_id": "buy",
        "exchange": exchange,
        "tradingsymbol": symbol,
        "transaction_type": "BUY",
        "variety": "regular",
        "product": "MIS",
        "order_type": "MARKET",
        "quantity": quantity,
        "average_price": buy_price
    }])

    sell_charges = kite.order_charges([{
        "order_id": "sell",
        "exchange": exchange,
        "tradingsymbol": symbol,
        "transaction_type": "SELL",
        "variety": "regular",
        "product": "MIS",
        "order_type": "MARKET",
        "quantity": quantity,
        "average_price": sell_price
    }])

    gross_pnl = (sell_price - buy_price) * quantity
    total_charges = buy_charges[0]['charges']['total'] + sell_charges[0]['charges']['total']
    net_pnl = gross_pnl - total_charges

    return {
        'gross_pnl': gross_pnl,
        'charges': total_charges,
        'net_pnl': net_pnl
    }
```

---

## Important Notes

1. **JSON POST**: These endpoints require JSON body, not form-encoded
2. **average_price required**: For charges API, must be non-zero
3. **Basket charges**: Use individual order charges, not final block
4. **Position consideration**: Set `consider_positions=true` for accurate spread benefits
5. **Rate limits**: 10 requests/second

---

_Last Updated: December 2025_
