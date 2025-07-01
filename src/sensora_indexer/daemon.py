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
    level=logging.INFO, # Start with INFO
    format='%(asctime)s - %(levelname)s - [%(name)s] %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)

# --- Create a Socket.IO Client Instance ---
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0, # Infinite
    reconnection_delay=5,
    reconnection_delay_max=60,
)

# --- Event Handlers for the '/global' Namespace ---

@sio.event(namespace="/global")
def connect():
    """
    Called upon successful connection to the namespace.
    We will now attempt to join the mempool room.
    """
    logger.info(f"Socket.IO connection established! (sid: {sio.sid})")
    logger.info("Attempting to subscribe to the 'mempool' room...")
    try:
        # 'join' is a common event name for subscribing to rooms/channels
        sio.emit('join', 'mempool', namespace="/global")
        logger.info("Sent 'join mempool' subscription request.")
    except Exception as e:
        logger.exception(f"Error sending subscription request: {e}")

@sio.event(namespace="/global")
def connect_error(data):
    logger.error(f"Socket.IO connection failed! Data: {data}")

@sio.event(namespace="/global")
def disconnect():
    logger.warning("Socket.IO disconnected. The client will attempt to reconnect automatically.")

@sio.on('tx', namespace="/global")
def on_tx(data):
    """
    This handler should now be triggered if our 'join mempool' subscription works.
    """
    logger.debug(f"Received 'tx' event data: {json.dumps(data)}")
    try:
        # Before full processing, do a quick string check for our prefix
        raw_message = json.dumps(data)
        if config.ADVERTISEMENT_PREFIX.hex() not in raw_message:
            return # Discard silently if it's not ours
        
        # If we passed the filter, it's worth processing
        logger.info("Potential advertisement transaction received. Processing...")
        process_transaction(data)
    except Exception as e:
        logger.exception(f"Error processing 'tx' event: {e}")

def process_transaction(tx_data: dict):
    # ... (This function remains the same robust version as before) ...
    tx_content = tx_data.get('tx', tx_data)
    txid = tx_content.get('h') or tx_content.get('txid')
    if not txid: return
    outputs = tx_content.get('out') or tx_content.get('outputs', [])
    if not outputs: return

    for output in outputs:
        script_hex = output.get('s2') or output.get('script')
        if not script_hex and 'scriptPubKey' in output and isinstance(output['scriptPubKey'], dict):
            script_hex = output['scriptPubKey'].get('hex')
        if not script_hex: continue
        
        if script_hex.startswith("006a") or script_hex.startswith("6a"):
            op_return_data = protocols.parse_op_return_from_script_hex(script_hex)
            if op_return_data:
                adv_data = protocols.parse_advertisement_payload(op_return_data)
                if adv_data:
                    logger.info(f"Advertisement VERIFIED! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data['txid'] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return

# --- Main Daemon Function ---
def main():
    logger.info("--- Starting Sensōra Indexer Daemon (Socket.IO Real-Time Mode) ---")
    database.init_registry_db()
    
    while True:
        try:
            url = config.BITAILS_API_BASE_URL
            logger.info(f"Connecting to {url} and namespace /global...")
            sio.connect(url, namespaces=["/global"], transports=['websocket', 'polling'])
            sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
        except Exception as e:
            logger.exception(f"Unhandled exception in daemon main loop: {e}")
        
        if sio.connected:
            sio.disconnect()
            
        logger.info("Restarting connection loop in 15 seconds...")
        time.sleep(15)

if __name__ == "__main__":
    main()