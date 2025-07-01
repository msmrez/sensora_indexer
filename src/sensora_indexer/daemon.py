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
    level=logging.DEBUG, # Kept at INFO to avoid noise from non-matching TXs
    format='%(asctime)s - %(levelname)s - [%(name)s] %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)

# --- Socket.IO Client ---
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0,
    reconnection_delay=5,
    reconnection_delay_max=60,
)

# --- Socket.IO Event Handlers for namespace '/global' ---

@sio.event(namespace="/global")
def connect():
    logger.info(f"Connected to Bitails (sid: {sio.sid}). Listening for all mempool transactions.")
    # No subscription query is sent. We will filter client-side.

@sio.event(namespace="/global")
def connect_error(data):
    logger.error(f"Connection failed. Data: {data}")

@sio.event(namespace="/global")
def disconnect():
    logger.warning("Disconnected from Bitails. Will retry.")

@sio.on("tx", namespace="/global")
def on_tx(data):
    """
    This event handler is called for EVERY transaction.
    We will perform a quick client-side filter before deep processing.
    """
    logger.debug(f"RAW 'tx' EVENT DATA RECEIVED: {json.dumps(data, indent=2)}")
        try:
        process_transaction(data)
    except Exception as e:
        logger.exception(f"Error processing 'tx' event during debug: {e}")

        
    try:
        # --- START CLIENT-SIDE FILTER ---
        # Convert the incoming data to a string for a quick substring check.
        # This is very fast and avoids full JSON parsing for every single transaction.
        raw_message = json.dumps(data)
        
        # We are looking for our advertisement prefix in hex format.
        if config.ADVERTISEMENT_PREFIX.hex() not in raw_message:
            # If the prefix isn't in the raw message, discard it immediately.
            return 
        # --- END CLIENT-SIDE FILTER ---

        # If we passed the filter, it's likely our transaction. Now we process it fully.
        logger.info("Potential advertisement transaction received. Processing...")
        logger.debug(f"Filtered TX Data: {raw_message}") # Log the data for debug if needed
        process_transaction(data)

    except Exception as e:
        logger.exception(f"Error in 'tx' handler: {e}")

def process_transaction(tx_data: dict):
    """
    Processes a single transaction dictionary that has already been pre-filtered.
    """
    tx_content = tx_data.get("tx", tx_data)
    txid = tx_content.get("h") or tx_content.get("txid")
    if not txid:
        return

    outputs = tx_content.get("out") or tx_content.get("outputs", [])
    for output in outputs:
        script_hex = output.get("s2") or output.get("script")
        if not script_hex and 'scriptPubKey' in output and isinstance(output['scriptPubKey'], dict):
            script_hex = output['scriptPubKey'].get('hex')
        if not script_hex:
            continue

        if script_hex.startswith("006a") or script_hex.startswith("6a"):
            op_return_data = protocols.parse_op_return_from_script_hex(script_hex)
            if op_return_data:
                adv_data = protocols.parse_advertisement_payload(op_return_data)
                if adv_data:
                    logger.info(f"Advertisement found and VERIFIED! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data["txid"] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return

# --- Main Daemon Entry Point ---
def main():
    logger.info("--- Starting Sensōra Indexer Daemon ---")
    database.init_registry_db()
    while True:
        try:
            url = config.BITAILS_API_BASE_URL
            logger.info(f"Connecting to {url} on namespace /global")
            sio.connect(url, namespaces=["/global"], transports=["websocket", "polling"])
            sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
        except Exception as e:
            logger.exception(f"Unhandled exception in main loop: {e}")
        if sio.connected:
            sio.disconnect()
        logger.info("Retrying in 15 seconds...")
        time.sleep(15)

if __name__ == "__main__":
    main()