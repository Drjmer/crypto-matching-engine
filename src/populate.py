import asyncio
import websockets
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    filename='../logs/populate_order_book.log',
    filemode='a'
)

async def submit_order(order):
    """Submit an order to the Order Submission API."""
    try:
        async with await asyncio.wait_for(websockets.connect("ws://localhost:8765"), timeout=5) as ws:
            await ws.send(json.dumps(order))
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            logging.info(f"Order response: {response}")
            return json.loads(response)
    except Exception as e:
        logging.error(f"Order submission failed: {e}")
        return None

async def populate_orders():
    """Add sell orders to populate asks."""
    orders = [
        {"symbol": "BTC-USDT", "order_type": "limit", "side": "sell", "quantity": 0.5, "price": 30000.0},
        {"symbol": "BTC-USDT", "order_type": "limit", "side": "sell", "quantity": 0.3, "price": 30010.0},
        {"symbol": "BTC-USDT", "order_type": "limit", "side": "sell", "quantity": 0.2, "price": 30020.0},
        {"symbol": "BTC-USDT", "order_type": "limit", "side": "buy", "quantity": 0.4, "price": 29990.0}
    ]
    for order in orders:
        response = await submit_order(order)
        if response and response.get("status") == "resting":
            print(f"Added {order['side']} order: {order['quantity']} at {order['price']}")
        else:
            print(f"Failed to add order: {order}, Response: {response}")

if __name__ == "__main__":
    asyncio.run(populate_orders())