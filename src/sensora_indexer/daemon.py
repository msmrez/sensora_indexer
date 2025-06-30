# sensora_indexer/src/sensora_indexer/daemon.py

import json
import logging
import time
import socketio

# Import our project modules
from . import config
from . import database
from . import protocols

# --- Logging Setup ---
# (Should be in the main app entry point)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Create a Socket.IO Client Instance ---
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0, # 0 means infinite retries
    reconnection_delay=5,
    reconnection_delay_max=30
)

# --- Define Socket.IO Event Handlers ---

@sio.event
def connect():
    logger.info("Socket.IO connection established successfully!")
    # NOTE: In Socket.IO, you don't typically send a subscription query message.
    # The server might automatically put you in a default room or 'namespace'.
    # If a specific subscription or room join is needed, it would be done here.
    # sio.emit('subscribe', {'channel': 'transactions'}) # Example if needed

@sio.event
def connect_error(data):
    logger.error(f"Socket.IO connection failed! Data: {data}")

@sio.event
def disconnect():
    logger.warning("Socket.IO disconnected.")

@sio.on('tx')
def on_tx(data):
    """
    This event handler is called whenever the server sends a 'tx' event.
    """
    try:
        logger.debug(f"Received 'tx' event data: {data}")
        
        # Based on your JS code, 'data' is the transaction object.
        # Let's process it.
        process_transaction(data)

    except Exception as e:
        logger.exception(f"Error processing 'tx' event: {e}")

def process_transaction(tx_data: dict):
    """
    Processes a single transaction dictionary to check for an advertisement.
    (This function can be reused from the polling version)
    """
    # Bitails WebSocket 'tx' event nests the tx data
    tx_content = tx_data.get('tx', {})
    txid = tx_content.get('h') # 'h' is the hash/txid
    
    if not txid:
        logger.warning(f"Received tx event with no txid: {tx_data}")
        return

    outputs = tx_content.get('out', [])
    for output in outputs:
        # The script hex is in 's2'
        script_hex = output.get('s2')
        if not script_hex:
            continue
        
        if script_hex.startswith("006a") or script_hex.startswith("6a"):
            op_return_data = protocols.parse_op_return_from_script_hex(script_hex)
            if op_return_data:
                adv_data = protocols.parse_advertisement_payload(op_return_data)
                if adv_data:
                    logger.info(f"Advertisement found! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data['txid'] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return # Found it, stop processing outputs for this tx

# --- Main Daemon Function ---

def main():
    """
    Main function to initialize the database and start the Socket.IO listener.
    """
    logger.info("--- Starting Sensōra Indexer Daemon (Socket.IO Mode) ---")
    database.init_registry_db()

    # Backfill logic could be added here to run before connecting.
    
    while True:
        try:
            logger.info(f"Attempting to connect to Bitails Socket.IO at {config.BITAILS_WEBSOCKET_URL}...")
            # The URL should be the base HTTPS URL, the library handles the path.
            # e.g., "https://api.bitails.io" and namespace="/global"
            # Based on your JS, it seems the full URL is the endpoint.
            sio.connect(config.BITAILS_WEBSOCKET_URL, transports=['websocket', 'polling'])
            
            # This will block until the connection is closed.
            sio.wait()

        except socketio.exceptions.ConnectionError as e:
            logger.error(f"Socket.IO connection error: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"An uncaught error occurred in the daemon: {e}")
        
        logger.info("Attempting to reconnect in 10 seconds...")
        time.sleep(10)

if __name__ == "__main__":
    main()