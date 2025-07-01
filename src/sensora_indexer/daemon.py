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
logging.basicConfig(
    level=logging.DEBUG, # <--- CHANGE TO DEBUG to see all messages
    format='%(asctime)s - %(levelname)s - [%(name)s] %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger('socketio').setLevel(logging.INFO) # Keep library logs quieter
logging.getLogger('engineio').setLevel(logging.INFO)

# --- Create a Socket.IO Client Instance ---
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0, 
    reconnection_delay=5,
    reconnection_delay_max=60,
    logger=True, # Enable socketio's own verbose logging
    engineio_logger=True
)

# --- Define Socket.IO Event Handlers ---

@sio.event
def connect():
    logger.info(f"Socket.IO connection established! (sid: {sio.sid})")

@sio.event
def connect_error(data):
    logger.error(f"Socket.IO connection failed! Data: {data}")

@sio.event
def disconnect():
    logger.warning("Socket.IO disconnected. The client will attempt to reconnect automatically.")

# --- NEW: Catch-all event handler for debugging ---
@sio.on('*')
def catch_all(event, data):
    logger.debug(f"Caught event '{event}' with data: {json.dumps(data, indent=2)}")

@sio.on('tx')
def on_tx(data):
    """
    This event handler is called whenever the server sends a 'tx' event.
    """
    try:
        # The catch_all handler already logs this, but we can keep it for clarity
        logger.info("Received 'tx' event. Processing...")
        process_transaction(data)
    except Exception as e:
        logger.exception(f"Error processing 'tx' event: {e}")

def process_transaction(tx_data: dict):
    # ... (the rest of your process_transaction function remains the same)
    tx_content = tx_data.get('tx', tx_data)
    txid = tx_content.get('h') or tx_content.get('txid')
    if not txid:
        logger.debug(f"Received event with no parsable txid: {tx_data}")
        return
    outputs = tx_content.get('out') or tx_content.get('outputs', [])
    if not outputs:
        return
    for output in outputs:
        script_hex = output.get('s2') or output.get('script')
        if not script_hex and 'scriptPubKey' in output and isinstance(output['scriptPubKey'], dict):
            script_hex = output['scriptPubKey'].get('hex')
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
                    return

# --- Main Daemon Function ---
# ... (The main() function remains the same)
def main():
    logger.info("--- Starting Sensōra Indexer Daemon (Socket.IO Mode) ---")
    database.init_registry_db()
    while True:
        try:
            logger.info(f"Attempting to connect to Bitails Socket.IO at {config.BITAILS_API_BASE_URL + '/global'}")
            sio.connect(config.BITAILS_API_BASE_URL + "/global", transports=['websocket', 'polling'])
            sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.error(f"Socket.IO connection error: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"An uncaught error occurred in the daemon's main loop: {e}")
        if sio.connected:
            sio.disconnect()
        logger.info("Restarting connection loop in 15 seconds...")
        time.sleep(15)

if __name__ == "__main__":
    main()