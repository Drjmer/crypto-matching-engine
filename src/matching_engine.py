import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from collections import deque
from order import Order
from order_book import OrderBook
import unittest

# Configure main logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='../logs/matching_engine.log',
    filemode='a'
)

# Configure bids logging
bids_logger = logging.getLogger('bids')
bids_handler = logging.FileHandler('../logs/bids.log', mode='a')
bids_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
bids_logger.addHandler(bids_handler)
bids_logger.setLevel(logging.INFO)

# Configure asks logging
asks_logger = logging.getLogger('asks')
asks_handler = logging.FileHandler('../logs/asks.log', mode='a')
asks_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
asks_logger.addHandler(asks_handler)
asks_logger.setLevel(logging.INFO)

class MatchingEngine:
    def __init__(self):
        self.order_books = {}  # Symbol -> OrderBook
        self.trade_subscribers = set()
        self.market_data_subscribers = set()

    def get_order_book(self, symbol):
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBook(symbol)
        return self.order_books[symbol]

    async def process_order(self, order_data):
        try:
            # Validate order
            symbol = order_data.get("symbol")
            order_type = order_data.get("order_type")
            side = order_data.get("side")
            quantity = order_data.get("quantity")
            price = order_data.get("price")

            if not all([symbol, order_type, side, quantity]):
                raise ValueError("Missing required fields: symbol, order_type, side, quantity")
            if order_type not in ["market", "limit", "ioc", "fok"]:
                raise ValueError(f"Invalid order type: {order_type}")
            if side not in ["buy", "sell"]:
                raise ValueError(f"Invalid side: {side}")

            try:
                quantity = float(quantity)
                if quantity <= 0:
                    raise ValueError("Quantity must be positive")
                if order_type != "market":
                    if price is None:
                        raise ValueError(f"Price required for {order_type} orders")
                    price = float(price)
                    if price <= 0:
                        raise ValueError("Price must be positive")
                else:
                    price = None
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid quantity or price format: {str(e)}")

            order = Order(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                order_type=order_type,
                side=side,
                quantity=quantity,
                price=price
            )
            logging.info(f"Processing {order.side} {order.order_type} order {order.order_id}: {order.quantity} at {order.price}")

            order_book = self.get_order_book(symbol)
            trades = []
            remaining_quantity = order.quantity

            # FOK pre-check
            if order_type == "fok":
                available_qty = 0
                target_book = order_book.asks if side == "buy" else order_book.bids
                for price_level, orders in target_book.items():
                    if side == "buy" and order.price is not None and price_level > order.price:
                        continue
                    if side == "sell" and order.price is not None and price_level < order.price:
                        continue
                    available_qty += sum(o.quantity for o in orders)
                if available_qty < order.quantity:
                    logging.info(f"FOK order {order.order_id} canceled: insufficient quantity ({available_qty} < {order.quantity})")
                    snapshot = order_book.get_l2_snapshot(depth=10)
                    bids_logger.info("Top 10 Bids: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['bids']])
                    asks_logger.info("Top 10 Asks: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['asks']])
                    bids_handler.flush()
                    asks_handler.flush()
                    return {"order_id": order.order_id, "trades": [], "status": "canceled"}

            # Determine if order is marketable
            best_bid = order_book.bids.peekitem(0)[0] if order_book.bids else None
            best_ask = order_book.asks.peekitem(0)[0] if order_book.asks else None
            logging.info(f"Marketability check: side={side}, order_type={order_type}, price={order.price}, best_bid={best_bid}, best_ask={best_ask}")
            is_marketable = order_type == "market" or (
                (side == "buy" and best_ask is not None and (order.price is None or order.price >= best_ask)) or
                (side == "sell" and best_bid is not None and (order.price is None or order.price <= best_bid))
            )
            logging.info(f"Order {order.order_id} is_marketable={is_marketable}")

            # Add non-marketable limit orders
            if order_type == "limit" and not is_marketable:
                order_book.add_order(order)
                logging.info(f"Added {order.side} order {order.order_id} at {order.price} for {order.quantity} {symbol}")
                snapshot = order_book.get_l2_snapshot(depth=10)
                bids_logger.info("Top 10 Bids: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['bids']])
                asks_logger.info("Top 10 Asks: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['asks']])
                bids_handler.flush()
                asks_handler.flush()
                return {"order_id": order.order_id, "trades": [], "status": "resting"}

            # Try matching if marketable
            if is_marketable:
                if side == "buy":
                    trades, remaining_quantity = self.match_buy_order(order, order_book)
                else:  # sell
                    trades, remaining_quantity = self.match_sell_order(order, order_book)

            # Handle remaining quantity
            status = "filled" if abs(remaining_quantity) < 1e-8 else "partial"
            if remaining_quantity > 1e-8:
                if order_type in ["ioc", "fok"]:
                    status = "canceled"
                    logging.info(f"{order_type.upper()} order {order.order_id} canceled: remaining {remaining_quantity}")
                elif order_type == "market":
                    status = "canceled"
                    logging.info(f"Market order {order.order_id} canceled: remaining {remaining_quantity}")
                elif order_type == "limit":
                    order.quantity = round(remaining_quantity, 8)
                    order_book.add_order(order)
                    status = "resting"
                    logging.info(f"Added remaining {order.side} order {order.order_id} at {order.price} for {order.quantity} {symbol}")

            # Broadcast updates
            for trade in trades:
                await self.broadcast_trade(trade)
            snapshot = order_book.get_l2_snapshot(depth=10)
            await self.broadcast_market_data(snapshot)

            # Log top 10 bids and asks
            logging.debug(f"Snapshot for logging: {snapshot}")
            bids_logger.info("Top 10 Bids: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['bids']])
            asks_logger.info("Top 10 Asks: %s", [[round(p, 2), round(q, 8)] for p, q in snapshot['asks']])
            bids_handler.flush()
            asks_handler.flush()

            return {"order_id": order.order_id, "trades": trades, "status": status}

        except Exception as e:
            logging.error(f"Error processing order: {str(e)}", exc_info=True)
            return {"order_id": str(uuid.uuid4()), "trades": [], "status": "error", "error": str(e)}

    def match_buy_order(self, order, order_book):
        trades = []
        remaining_quantity = round(order.quantity, 8)
        asks_to_remove = []

        logging.info(f"Matching buy order {order.order_id}: {order.quantity} at {order.price}")
        logging.info(f"Current asks: {[(p, [round(o.quantity, 8) for o in orders]) for p, orders in order_book.asks.items()]}")

        for price in list(order_book.asks.keys()):
            if order.order_type in ["limit", "ioc", "fok"] and order.price is not None and price > order.price:
                continue
            orders = order_book.asks.get(price, deque())
            for ask in list(orders):
                if remaining_quantity <= 1e-8:
                    break
                matched_quantity = min(round(remaining_quantity, 8), round(ask.quantity, 8))
                trades.append({
                    "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
                    "symbol": order.symbol,
                    "trade_id": str(uuid.uuid4()),
                    "price": price,
                    "quantity": matched_quantity,
                    "aggressor_side": "buy",
                    "maker_order_id": ask.order_id,
                    "taker_order_id": order.order_id
                })
                remaining_quantity = round(remaining_quantity - matched_quantity, 8)
                ask.quantity = round(ask.quantity - matched_quantity, 8)
                if ask.quantity <= 1e-8:
                    asks_to_remove.append((price, ask))
                logging.info(f"Matched {matched_quantity} at {price}")

        for price, ask in asks_to_remove:
            orders = order_book.asks.get(price, deque())
            if ask in orders:
                orders.remove(ask)
                if not orders:
                    del order_book.asks[price]
                order_book.remove_order(ask.order_id)

        return trades, remaining_quantity

    def match_sell_order(self, order, order_book):
        trades = []
        remaining_quantity = round(order.quantity, 8)
        bids_to_remove = []

        logging.info(f"Matching sell order {order.order_id}: {order.quantity} at {order.price}")
        logging.info(f"Current bids: {[(p, [round(o.quantity, 8) for o in orders]) for p, orders in order_book.bids.items()]}")

        for price in list(order_book.bids.keys()):
            if order.order_type in ["limit", "ioc", "fok"] and order.price is not None and price < order.price:
                continue
            orders = order_book.bids.get(price, deque())
            for bid in list(orders):
                if remaining_quantity <= 1e-8:
                    break
                matched_quantity = min(round(remaining_quantity, 8), round(bid.quantity, 8))
                trades.append({
                    "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
                    "symbol": order.symbol,
                    "trade_id": str(uuid.uuid4()),
                    "price": price,
                    "quantity": matched_quantity,
                    "aggressor_side": "sell",
                    "maker_order_id": bid.order_id,
                    "taker_order_id": order.order_id
                })
                remaining_quantity = round(remaining_quantity - matched_quantity, 8)
                bid.quantity = round(bid.quantity - matched_quantity, 8)
                if bid.quantity <= 1e-8:
                    bids_to_remove.append((price, bid))
                logging.info(f"Matched {matched_quantity} at {price}")

        for price, bid in bids_to_remove:
            orders = order_book.bids.get(price, deque())
            if bid in orders:
                orders.remove(bid)
                if not orders:
                    del order_book.bids[price]
                order_book.remove_order(bid.order_id)

        return trades, remaining_quantity

    async def broadcast_trade(self, trade):
        message = json.dumps(trade)
        disconnected = set()
        for ws in self.trade_subscribers:
            try:
                await ws.send(message)
            except Exception as e:
                logging.error(f"Error broadcasting trade: {str(e)}")
                disconnected.add(ws)
        self.trade_subscribers -= disconnected

    async def broadcast_market_data(self, snapshot):
        message = json.dumps(snapshot)
        disconnected = set()
        for ws in self.market_data_subscribers:
            try:
                await ws.send(message)
            except Exception as e:
                logging.error(f"Error broadcasting market data: {str(e)}")
                disconnected.add(ws)
        self.market_data_subscribers -= disconnected

class TestMatchingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()
        self.engine.order_books["BTC-USDT"] = OrderBook("BTC-USDT")

    def test_limit_order_matching(self):
        """Test limit order matching with partial fill."""
        sell_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "sell",
            "quantity": 0.5,
            "price": 30000.0
        }
        result = asyncio.run(self.engine.process_order(sell_order))
        self.assertEqual(result["status"], "resting")

        buy_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "buy",
            "quantity": 1.0,
            "price": 30005.0
        }
        result = asyncio.run(self.engine.process_order(buy_order))
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["price"], 30000.0)
        self.assertEqual(result["trades"][0]["quantity"], 0.5)
        self.assertEqual(result["status"], "resting")

    def test_market_order_matching(self):
        """Test market order matching."""
        sell_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "sell",
            "quantity": 0.5,
            "price": 30000.0
        }
        asyncio.run(self.engine.process_order(sell_order))

        buy_order = {
            "symbol": "BTC-USDT",
            "order_type": "market",
            "side": "buy",
            "quantity": 0.5
        }
        result = asyncio.run(self.engine.process_order(buy_order))
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["price"], 30000.0)
        self.assertEqual(result["trades"][0]["quantity"], 0.5)
        self.assertEqual(result["status"], "filled")

    def test_fok_order(self):
        """Test FOK order cancellation if not fully filled."""
        sell_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "sell",
            "quantity": 0.5,
            "price": 30000.0
        }
        asyncio.run(self.engine.process_order(sell_order))

        buy_order = {
            "symbol": "BTC-USDT",
            "order_type": "fok",
            "side": "buy",
            "quantity": 1.0,
            "price": 30005.0
        }
        result = asyncio.run(self.engine.process_order(buy_order))
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["status"], "canceled")

    def test_sell_limit_matches_bid(self):
        """Test sell limit order matching with higher bid."""
        buy_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "buy",
            "quantity": 0.5,
            "price": 30005.0
        }
        result = asyncio.run(self.engine.process_order(buy_order))
        self.assertEqual(result["status"], "resting")

        sell_order = {
            "symbol": "BTC-USDT",
            "order_type": "limit",
            "side": "sell",
            "quantity": 0.5,
            "price": 30000.0
        }
        result = asyncio.run(self.engine.process_order(sell_order))
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["price"], 30005.0)
        self.assertEqual(result["trades"][0]["quantity"], 0.5)
        self.assertEqual(result["status"], "filled")

if __name__ == "__main__":
    unittest.main()