# sensora_indexer/indexer_daemon.py

import asyncio
import json
import logging
import websockets
from websockets.exceptions import ConnectionClosed

# Import our project modules
from . import config, database, protocols

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def process_transaction(tx_data: dict):
    """
    Processes a single transaction to see if it's a sensor advertisement.
    """
    txid = tx_data.get('h')
    if not txid:
        return # Not a valid transaction format

    outputs = tx_data.get('out', [])
    for output in outputs:
        script_hex = output.get('s2') # 's2' is often the hex script in bitcoind-like APIs
        if not script_hex:
            continue
        
        # Check if it's an OP_RETURN
        if script_hex.startswith("006a") or script_hex.startswith("6a"):
            op_return_data = protocols.parse_op_return_from_script_hex(script_hex)
            if op_return_data:
                # Check if it's our advertisement protocol
                adv_data = protocols.parse_advertisement_payload(op_return_data)
                if adv_data:
                    logger.info(f"Advertisement found! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    # Add the txid to the data dict before saving
                    adv_data['txid'] = txid
                    # Save the parsed data to our registry database
                    database.upsert_sensor_advertisement(adv_data)
                    # Once found, we can stop processing other outputs of this tx
                    return

async def listen_to_bitails_websocket():
    """
    Connects to the bitails.io WebSocket and processes incoming transactions.
    """
    uri = config.BITAILS_WEBSOCKET_URL
    query = {
        "v": 3,
        "q": {
            "find": {"out.s2": {"$regex": f"^(00)?6a.*{config.ADVERTISEMENT_PREFIX.hex()}"}},
            "project": {"h": 1, "out.s2": 1, "_id": 0}
        }
    }

    logger.info(f"Connecting to WebSocket at {uri}...")
    while True: # Main loop to handle reconnects
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("WebSocket connection established. Subscribing to transaction stream.")
                await websocket.send(json.dumps(query))
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        # The data is usually wrapped in a list under the 'data' key
                        if data.get('type') == 'data' and 'data' in data:
                            for tx in data['data']:
                                await process_transaction(tx)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode JSON from WebSocket message: {message}")
                    except Exception as e:
                        logger.exception(f"Error processing WebSocket message: {e}")

        except ConnectionClosed as e:
            logger.error(f"WebSocket connection closed unexpectedly: {e}. Reconnecting in 10 seconds...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.exception(f"An unexpected error occurred in the WebSocket listener: {e}. Retrying in 30 seconds...")
            await asyncio.sleep(30)

def main():
    """
    Main function to initialize the database and start the WebSocket listener.
    """
    logger.info("--- Starting Sensōra Indexer Daemon ---")
    database.init_registry_db()
    
    # We could also add the block backfill logic here before starting the listener
    # For now, we'll just start listening for new transactions.
    
    try:
        asyncio.run(listen_to_bitails_websocket())
    except KeyboardInterrupt:
        logger.info("Indexer daemon stopped by user.")
    except Exception as e:
        logger.exception(f"Indexer daemon crashed: {e}")

if __name__ == "__main__":
    main()