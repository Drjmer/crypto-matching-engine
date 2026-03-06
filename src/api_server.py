import asyncio
import websockets
import json
import logging
from matching_engine import MatchingEngine
import uuid
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='..logs/api_server.log',
    filemode='a'
)

async def handle_order_submission(ws, engine):
    """Handle order submissions on port 8765."""
    try:
        async for message in ws:
            try:
                start_time = datetime.now()
                order_data = json.loads(message)
                logging.info(f"Received order: {order_data}")
                response = await engine.process_order(order_data)
                await ws.send(json.dumps(response))
                elapsed = (datetime.now() - start_time).total_seconds() * 1000
                logging.debug(f"Processed order in {elapsed:.2f} ms")
            except json.JSONDecodeError:
                logging.error("Invalid JSON received")
                await ws.send(json.dumps({"order_id": str(uuid.uuid4()), "trades": [], "status": "error", "error": "Invalid JSON"}))
            except Exception as e:
                logging.error(f"Order processing error: {str(e)}")
                await ws.send(json.dumps({"order_id": str(uuid.uuid4()), "trades": [], "status": "error", "error": str(e)}))
    except websockets.exceptions.ConnectionClosed:
        logging.info("Order submission connection closed")
    except Exception as e:
        logging.error(f"Order submission handler error: {str(e)}")

async def handle_market_data_subscription(ws, engine):
    """Handle market data subscriptions on port 8766."""
    try:
        engine.market_data_subscribers.add(ws)
        # Send initial snapshot
        order_book = engine.get_order_book("BTC-USDT")
        snapshot = order_book.get_l2_snapshot(depth=10)
        logging.info(f"Sending market data snapshot: {snapshot}")
        await ws.send(json.dumps(snapshot))
        async for _ in ws:
            # Optionally send updates on order book changes
            pass
    except websockets.exceptions.ConnectionClosed:
        logging.info("Market data subscription connection closed")
    except Exception as e:
        logging.error(f"Market data subscription error: {str(e)}")
    finally:
        engine.market_data_subscribers.discard(ws)

async def handle_trade_subscription(ws, engine):
    """Handle trade subscriptions on port 8767."""
    try:
        engine.trade_subscribers.add(ws)
        async for _ in ws:
            pass
    except websockets.exceptions.ConnectionClosed:
        logging.info("Trade subscription connection closed")
    except Exception as e:
        logging.error(f"Trade subscription error: {str(e)}")
    finally:
        engine.trade_subscribers.discard(ws)

async def start_server():
    """Start WebSocket servers."""
    engine = MatchingEngine()
    try:
        async with websockets.serve(
            lambda ws: handle_order_submission(ws, engine),
            "localhost", 8765
        ) as order_server, websockets.serve(
            lambda ws: handle_market_data_subscription(ws, engine),
            "localhost", 8766
        ) as market_data_server, websockets.serve(
            lambda ws: handle_trade_subscription(ws, engine),
            "localhost", 8767
        ) as trade_server:
            logging.info("Servers started on ports 8765, 8766, 8767")
            for server in [order_server, market_data_server, trade_server]:
                for socket in server.sockets:
                    logging.info(f"Server listening on {socket.getsockname()[0]}:{socket.getsockname()[1]}")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logging.error(f"Server error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(start_server())