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
    level=logging.INFO, # Set to DEBUG to see raw messages
    format='%(asctime)s - %(levelname)s - [%(name)s] %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger('socketio').setLevel(logging.WARNING) # Quieten socketio library logs
logging.getLogger('engineio').setLevel(logging.WARNING)

# --- Create a Socket.IO Client Instance ---
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0, # 0 means infinite retries
    reconnection_delay=5,    # Start with 5s delay
    reconnection_delay_max=60 # Max delay of 60s
)

# --- Define Socket.IO Event Handlers ---

@sio.event
def connect():
    logger.info(f"Socket.IO connection established! (sid: {sio.sid})")
    # Based on the JS example, we don't need to send a subscription.
    # The server seems to stream 'tx' events by default on the /global namespace.

@sio.event
def connect_error(data):
    logger.error(f"Socket.IO connection failed! Data: {data}")

@sio.event
def disconnect():
    logger.warning("Socket.IO disconnected. The client will attempt to reconnect automatically.")

@sio.on('tx')
def on_tx(data):
    """
    This event handler is called whenever the server sends a 'tx' event.
    """
    try:
        logger.debug(f"Received 'tx' event data: {json.dumps(data, indent=2)}")
        
        # Call our robust processing function
        process_transaction(data)

    except Exception as e:
        logger.exception(f"Error processing 'tx' event: {e}")

def process_transaction(tx_data: dict):
    """
    Processes a single transaction dictionary to check for an advertisement.
    """
    # The transaction data might be at the top level or nested under a 'tx' key.
    tx_content = tx_data.get('tx', tx_data)

    # The transaction ID key could be 'h' (hash) or 'txid'.
    txid = tx_content.get('h') or tx_content.get('txid')
    
    if not txid:
        logger.debug(f"Received event with no parsable txid: {tx_data}")
        return

    # The outputs key could be 'out' or 'outputs'.
    outputs = tx_content.get('out') or tx_content.get('outputs', [])
    if not outputs:
        return

    for output in outputs:
        # The script hex key could be 's2', 'script', or 'scriptPubKey.hex'.
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

def main():
    """
    Main function to initialize the database and start the Socket.IO listener.
    """
    logger.info("--- Starting Sensōra Indexer Daemon (Socket.IO Mode) ---")
    database.init_registry_db()
    
    # This loop ensures that if the client crashes for an unknown reason,
    # it will restart after a delay. The client library handles reconnects itself.
    while True:
        try:
            logger.info(f"Attempting to connect to Bitails Socket.IO at {config.BITAILS_API_BASE_URL}...")
            
            # The connect function takes the base URL. The library handles the handshake path.
            # The namespace is inferred from the URL path, so /global is correct.
            sio.connect(config.BITAILS_API_BASE_URL + "/global", transports=['websocket', 'polling'])
            
            # This blocks and keeps the script alive, processing events until disconnected.
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