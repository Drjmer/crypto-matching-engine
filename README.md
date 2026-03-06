
# GoQuant — Crypto Trading Engine

A high-performance, asynchronous cryptocurrency trading engine built in Python. GoQuant implements a real-time order matching system with a WebSocket API, supporting multiple order types and live market data streaming for the BTC-USDT trading pair.

---

## Features

* **Order Matching Engine** — Price-time priority matching with support for market, limit, IOC, and FOK order types
* **WebSocket API** — Three dedicated channels for order submission, market data, and trade feeds
* **L2 Order Book** — Real-time Level 2 snapshots with configurable depth using sorted data structures
* **Live Broadcasting** — Trade and order book updates pushed to all subscribers on every state change
* **Structured Logging** — Separate log files for the matching engine, bids, asks, and manual trades
* **Unit Tests** — Built-in test suite covering limit, market, FOK, and cross-side matching scenarios

---

## Project Structure

```
crypto-trading-engine/
├── src/
│   ├── api_server.py        # WebSocket server (ports 8765, 8766, 8767)
│   ├── matching_engine.py   # Core order matching logic + unit tests
│   ├── order_book.py        # Order book with sorted bid/ask price levels
│   ├── order.py             # Order data model
│   ├── populate.py          # Seed script to pre-fill the order book
│   └── manual_trade.py      # Interactive CLI for submitting trades
├── logs/
│   ├── matching_engine.log
│   ├── bids.log
│   ├── asks.log
│   ├── manual_trade.log
│   └── populate_order_book.log
└── requirements.txt
```

---

## Getting Started

### Prerequisites

* Python 3.10+

### Installation

```bash
git clone https://github.com/Drjmer/goquant.git
cd goquant/crypto-trading-engine
pip install -r requirements.txt
```

### Running the Server

```bash
cd src
python api_server.py
```

This starts three WebSocket servers:

| Port     | Purpose                    |
| -------- | -------------------------- |
| `8765` | Order submission           |
| `8766` | Market data (L2 snapshots) |
| `8767` | Trade feed                 |

### Seeding the Order Book

To pre-populate the order book with sample BTC-USDT resting orders:

```bash
python populate.py
```

### Manual Trading (CLI)

For an interactive terminal interface to submit orders:

```bash
python manual_trade.py
```

You'll be prompted to enter the order type, side, quantity, and price. The engine's response and the updated order book state are printed after each trade.

---

## API Reference

All communication is over WebSocket using JSON.

### Submit an Order — `ws://localhost:8765`

**Request:**

```json
{
  "symbol": "BTC-USDT",
  "order_type": "limit",
  "side": "buy",
  "quantity": 0.5,
  "price": 30000.0
}
```

| Field          | Type   | Required      | Description                              |
| -------------- | ------ | ------------- | ---------------------------------------- |
| `symbol`     | string | ✅            | Trading pair (e.g.`BTC-USDT`)          |
| `order_type` | string | ✅            | `market`,`limit`,`ioc`, or `fok` |
| `side`       | string | ✅            | `buy`or `sell`                       |
| `quantity`   | float  | ✅            | Positive number                          |
| `price`      | float  | Conditionally | Required for `limit`,`ioc`,`fok`   |

**Response:**

```json
{
  "order_id": "uuid",
  "status": "filled",
  "trades": [
    {
      "trade_id": "uuid",
      "timestamp": "2024-01-01T00:00:00Z",
      "symbol": "BTC-USDT",
      "price": 30000.0,
      "quantity": 0.5,
      "aggressor_side": "buy",
      "maker_order_id": "uuid",
      "taker_order_id": "uuid"
    }
  ]
}
```

Possible `status` values: `filled`, `partial`, `resting`, `canceled`, `error`

---

### Market Data — `ws://localhost:8766`

On connect, the server immediately sends an L2 snapshot. Subsequent updates are pushed on every order book change.

```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "symbol": "BTC-USDT",
  "bids": [[30000.0, 0.5], [29990.0, 0.4]],
  "asks": [[30010.0, 0.3], [30020.0, 0.2]]
}
```

---

### Trade Feed — `ws://localhost:8767`

Each executed trade is broadcast in real time:

```json
{
  "trade_id": "uuid",
  "timestamp": "2024-01-01T00:00:00Z",
  "symbol": "BTC-USDT",
  "price": 30000.0,
  "quantity": 0.5,
  "aggressor_side": "buy",
  "maker_order_id": "uuid",
  "taker_order_id": "uuid"
}
```

---

## Order Types

| Type                               | Behavior                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------- |
| **Market**                   | Executes immediately at the best available price. Canceled if no liquidity.                 |
| **Limit**                    | Executes at the specified price or better. Rests in the book if not immediately marketable. |
| **IOC**(Immediate or Cancel) | Fills as much as possible immediately; any unfilled remainder is canceled.                  |
| **FOK**(Fill or Kill)        | Must be filled in full immediately or the entire order is canceled.                         |

---

## Running Tests

Unit tests are embedded in `matching_engine.py` and cover:

* Limit order partial fill and resting
* Market order full fill
* FOK cancellation on insufficient liquidity
* Cross-side sell limit matching against a higher bid

```bash
cd src
python -m pytest matching_engine.py -v
# or
python matching_engine.py
```

---

## Dependencies

```
websockets==10.4
sortedcontainers==2.4.0
```

---

## License

MIT License. See [LICENSE](https://claude.ai/chat/LICENSE) for details.
