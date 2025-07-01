# sensora_indexer/src/sensora_indexer/daemon.py

import json
import logging
import time
import socketio
from . import database, protocols, config

# --- Logging Setup ---
# SET THE LEVEL TO INFO TO REDUCE NOISE NOW
logging.basicConfig(
    level=logging.INFO, # <--- Changed back to INFO
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
    # logger=True, # You can disable the verbose socketio logs now
    # engineio_logger=True
)

# --- Socket.IO Event Handlers for namespace '/global' ---

@sio.event(namespace="/global")
def connect():
    logger.info(f"Connected to Bitails (sid: {sio.sid}). Subscribing to filtered transactions...")
    try:
        # Define the query to filter for our specific OP_RETURN prefix
        # This asks the server to do the filtering for us.
        subscription_query = {
            "v": 3,
            "q": {
                "find": {
                    # This is a query for outputs where the hex script 's2'
                    # contains our advertisement prefix.
                    # This is less efficient than a regex but might be more stable.
                    # NOTE: This query syntax is an educated guess based on common APIs.
                    # It might need to be adjusted if it doesn't work.
                    "out.s2": { "$gte": f"6a{config.ADVERTISEMENT_PREFIX.hex()}" }
                },
                "project": {"tx.h": 1, "out": 1, "_id": 0}
            }
        }
        
        # In many Socket.IO APIs, you emit a message to join a "room" or set a "filter".
        # Let's try emitting a 'q' event with our query.
        sio.emit('q', subscription_query, namespace="/global")
        logger.info("Subscription query sent.")
        
    except Exception as e:
        logger.exception(f"Error during subscription: {e}")

@sio.event(namespace="/global")
def connect_error(data):
    logger.error(f"Connection failed. Data: {data}")

@sio.event(namespace="/global")
def disconnect():
    logger.warning("Disconnected from Bitails. Will retry.")

@sio.on("tx", namespace="/global")
def on_tx(data):
    logger.info("Received filtered 'tx' event, processing...")
    try:
        process_transaction(data)
    except Exception as e:
        logger.exception(f"Error in 'tx' handler: {e}")

# The catch-all is less necessary now that we're filtering, but can be kept for debug
# @sio.on("*", namespace="/global")
# def catch_all(event, data):
#     logger.debug(f"Caught event '{event}' with data: {json.dumps(data, indent=2)}")

def process_transaction(tx_data: dict):
    # This function remains the same, as it's designed to be robust.
    tx_content = tx_data.get("tx", tx_data)
    txid = tx_content.get("h") or tx_content.get("txid")
    if not txid:
        logger.debug(f"No txid in: {tx_data}")
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
                    logger.info(f"Advertisement found! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data["txid"] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return

# --- Main Daemon Entry Point ---
def main():
    # This main loop remains the same
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