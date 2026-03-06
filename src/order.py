import uuid
from datetime import datetime, timezone
class Order:
    def __init__(self, order_id, symbol, order_type, side, quantity, price=None, timestamp=None):
        self.order_id = order_id
        self.symbol = symbol
        self.order_type = order_type  # market, limit, ioc, fok
        self.side = side  # buy, sell
        self.quantity = float(quantity)
        self.price = float(price) if price is not None else None
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat() + 'Z'