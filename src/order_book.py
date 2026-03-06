import logging
from collections import deque
from sortedcontainers import SortedDict
from order import Order
from datetime import datetime, timezone

class OrderBook:
    def __init__(self, symbol):
        self.symbol = symbol
        self.bids = SortedDict(lambda x: -x)  # Descending order
        self.asks = SortedDict()  # Ascending order
        self.orders = {}  # Order ID -> Order

    def add_order(self, order):
        if order.order_id in self.orders:
            logging.error(f"Order ID {order.order_id} already exists")
            raise ValueError(f"Order ID {order.order_id} already exists")
        self.orders[order.order_id] = order
        price = order.price
        if order.side == "buy":
            if price not in self.bids:
                self.bids[price] = deque()
            self.bids[price].append(order)
        else:  # sell
            if price not in self.asks:
                self.asks[price] = deque()
            self.asks[price].append(order)
        logging.info(f"Added {order.side} order {order.order_id} at {price} for {order.quantity} {self.symbol}")

    def remove_order(self, order_id):
        if order_id not in self.orders:
            return
        order = self.orders[order_id]
        price = order.price
        if order.side == "buy":
            if price in self.bids and order in self.bids[price]:
                self.bids[price].remove(order)
                if not self.bids[price]:
                    del self.bids[price]
        else:  # sell
            if price in self.asks and order in self.asks[price]:
                self.asks[price].remove(order)
                if not self.asks[price]:
                    del self.asks[price]
        del self.orders[order_id]
        logging.info(f"Removed order {order_id}")

    def get_l2_snapshot(self, depth=10):
        bids = [[price, sum(o.quantity for o in orders)] for price, orders in list(self.bids.items())[:depth]]
        asks = [[price, sum(o.quantity for o in orders)] for price, orders in list(self.asks.items())[:depth]]
        return {
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',
            "symbol": self.symbol,
            "bids": bids,
            "asks": asks
        }