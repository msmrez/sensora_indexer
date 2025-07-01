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
    level=logging.DEBUG, # Kept at DEBUG to see all raw messages
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
    logger=True, # Enable socketio's own verbose logging for this debug session
    engineio_logger=True
)

# --- Define Socket.IO Event Handlers ---

@sio.event(namespace="/global")
def connect():
    logger.info(f"Socket.IO connection established! (sid: {sio.sid})")

@sio.event(namespace="/global")
def connect_error(data):
    logger.error(f"Socket.IO connection failed! Data: {data}")

@sio.event(namespace="/global")
def disconnect():
    logger.warning("Socket.IO disconnected. The client will attempt to reconnect automatically.")

# Catch-all handler for debugging to see all event names
@sio.on('*', namespace="/global")
def catch_all(event, data):
    # We only want to log the full data for the 'tx' event, others are less important
    if event == 'tx':
        logger.debug(f"Caught event '{event}'. Full data logged in on_tx handler.")
    else:
        logger.debug(f"Caught non-tx event '{event}'")

@sio.on('tx', namespace="/global")
def on_tx(data):
    """
    DEBUGGING VERSION: This handler logs the raw structure of EVERY 'tx' event.
    """
    # The 'try' block below should have the same indentation as this comment.
    logger.debug(f"RAW 'tx' EVENT DATA RECEIVED: {json.dumps(data, indent=2)}")
    
    try:
        # After logging, we attempt to process it to see if it works.
        process_transaction(data)
    except Exception as e:
        logger.exception(f"Error processing 'tx' event during debug: {e}")

def process_transaction(tx_data: dict):
    """
    Processes a single transaction dictionary to check for an advertisement.
    """
    tx_content = tx_data.get('tx', tx_data)
    txid = tx_content.get('h') or tx_content.get('txid')
    
    if not txid:
        # This is not a fatal error, just a message without a txid.
        # logger.debug(f"Received event with no parsable txid: {tx_data}")
        return

    # Check for our prefix in the raw data before full parsing
    raw_message = json.dumps(tx_data)
    if config.ADVERTISEMENT_PREFIX.hex() not in raw_message:
        return

    logger.info(f"Potential advertisement TX found ({txid[:10]}...). Performing full parse.")
    
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
                    logger.info(f"SUCCESS! Advertisement confirmed for TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data['txid'] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return

# --- Main Daemon Function ---
def main():
    logger.info("--- Starting Sensōra Indexer Daemon (Socket.IO Debug Mode) ---")
    database.init_registry_db()
    
    while True:
        try:
            url = config.BITAILS_API_BASE_URL
            logger.info(f"Connecting to {url} on namespace /global")
            sio.connect(url, namespaces=["/global"], transports=['websocket', 'polling'])
            sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
        except Exception as e:
            logger.exception(f"Unhandled exception in main loop: {e}")
        
        if sio.connected:
            sio.disconnect()
            
        logger.info("Restarting connection loop in 15 seconds...")
        time.sleep(15)

if __name__ == "__main__":
    main()