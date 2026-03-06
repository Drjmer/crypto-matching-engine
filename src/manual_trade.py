import asyncio
import json
import websockets
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='../logs/manual_trade.log',
    filemode='a'
)

async def submit_order(ws, order):
    """Submit a single order via WebSocket."""
    try:
        await ws.send(json.dumps(order))
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        logging.info(f"Submitted order: {order}, Response: {response}")
        print(f"\nTrade Response:\n{json.dumps(json.loads(response), indent=2)}")
        return json.loads(response)
    except Exception as e:
        logging.error(f"Error submitting order {order}: {str(e)}")
        print(f"Error: {str(e)}")
        return {"status": "error", "error": str(e)}

async def get_order_book_snapshot():
    """Retrieve the current order book state via WebSocket."""
    try:
        async with websockets.connect("ws://localhost:8766") as ws:
            snapshot = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            logging.info(f"Order book snapshot: {snapshot}")
            print("\nUpdated Order Book State for BTC-USDT:")
            print(f"Timestamp: {snapshot['timestamp']}")
            print("Bids:")
            for price, qty in snapshot.get('bids', []):
                print(f"  Price: ${price:.2f}, Quantity: {qty:.4f} BTC")
            print("Asks:")
            for price, qty in snapshot.get('asks', []):
                print(f"  Price: ${price:.2f}, Quantity: {qty:.4f} BTC")
            return snapshot
    except Exception as e:
        logging.error(f"Error retrieving snapshot: {str(e)}")
        print(f"Error retrieving snapshot: {str(e)}")
        return None

async def manual_trade():
    """Prompt for order details and submit a manual trade."""
    valid_order_types = {"market", "limit", "ioc", "fok"}
    valid_sides = {"buy", "sell"}
    print("Enter order details for manual trade (BTC-USDT):")
    symbol = "BTC-USDT"

    # Validate order type
    order_type = input("Order Type (market/limit/ioc/fok): ").strip().lower()
    while order_type not in valid_order_types:
        print(f"Invalid order type. Choose from {valid_order_types}")
        order_type = input("Order Type (market/limit/ioc/fok): ").strip().lower()

    # Validate side
    side = input("Side (buy/sell): ").strip().lower()
    while side not in valid_sides:
        print(f"Invalid side. Choose from {valid_sides}")
        side = input("Side (buy/sell): ").strip().lower()

    # Validate quantity
    while True:
        try:
            quantity = float(input("Quantity (e.g., 0.1): "))
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            break
        except ValueError as e:
            print(f"Invalid quantity: {e}")

    # Validate price (except for market orders)
    price = None
    if order_type != "market":
        while True:
            try:
                price = float(input("Price (e.g., 30001.0): "))
                if price <= 0:
                    raise ValueError("Price must be positive")
                break
            except ValueError as e:
                print(f"Invalid price: {e}")

    order = {
        "symbol": symbol,
        "order_type": order_type,
        "side": side,
        "quantity": quantity,
        "price": price
    }

    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            print(f"\nSubmitting order:\n{json.dumps(order, indent=2)}")
            response = await submit_order(ws, order)
            if response.get("status") == "error":
                print(f"Order submission failed: {response.get('error')}")
            await get_order_book_snapshot()
    except Exception as e:
        logging.error(f"Error executing manual trade: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(manual_trade())