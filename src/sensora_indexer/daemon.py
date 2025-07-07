# sensora_indexer/src/sensora_indexer/daemon.py

import json
import logging
import time
import requests
import sys

# Import our project modules
from . import config
from . import database
from . import protocols

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(module)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def process_transaction_data(tx_data: dict):
    """Processes a single full transaction dictionary to check for an advertisement."""
    txid = tx_data.get('txid')
    if not txid: return

    outputs = tx_data.get('outputs', [])
    for output in outputs:
        script_hex = output.get('script')
        if not script_hex: continue
        
        if script_hex.startswith("006a") or script_hex.startswith("6a"):
            op_return_data = protocols.parse_op_return_from_script_hex(script_hex)
            if op_return_data:
                adv_data = protocols.parse_advertisement_payload(op_return_data)
                if adv_data:
                    logger.info(f"Advertisement found in block! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
                    adv_data['txid'] = txid
                    database.upsert_sensor_advertisement(adv_data)
                    return # Stop processing other outputs

def get_block_op_return_txs(height: int) -> list[dict] | None:
    """
    Fetches details for only the transactions containing an OP_RETURN in a given block.
    """
    try:
        url = f"{config.BITAILS_API_BASE_URL}/block/height/{height}"
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        data = response.json()
        
        op_return_txs = []
        if 'transactionsDetails' in data and isinstance(data['transactionsDetails'], list):
            for tx_detail in data['transactionsDetails']:
                if 'op_return' in tx_detail.get('tags', []):
                    # This transaction has an OP_RETURN, add its txid for full fetching.
                    if tx_detail.get('txid'):
                        op_return_txs.append(tx_detail.get('txid'))
            return op_return_txs

        logger.error(f"Could not find 'transactionsDetails' list in block response for height {height}")
        return None
    except Exception as e:
        logger.exception(f"Failed to get and filter block content for height {height}: {e}")
        return None

def get_current_block_height() -> int | None:
    """Fetches the current block height from the blockchain info endpoint."""
    try:
        url = f"{config.BITAILS_API_BASE_URL}/network/info"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'blocks' in data and isinstance(data['blocks'], int):
            return data['blocks']
        logger.error(f"Could not find block height in bitails.io response: {data}")
        return None
    except Exception as e:
        logger.exception(f"Failed to get current block height: {e}")
        return None

def get_block_txids(height: int) -> list[str] | None:
    """Fetches all transaction IDs for a given block height."""
    try:
        url = f"{config.BITAILS_API_BASE_URL}/block/height/{height}"
        response = requests.get(url, timeout=45) # Blocks can be large, longer timeout
        response.raise_for_status()
        data = response.json()
        if 'tx' in data and isinstance(data['tx'], list):
            return data['tx']
        logger.error(f"Could not find transaction list in block response for height {height}")
        return None
    except Exception as e:
        logger.exception(f"Failed to get block content for height {height}: {e}")
        return None

def get_full_transaction(txid: str) -> dict | None:
    """Fetches full transaction details."""
    try:
        url = f"{config.BITAILS_API_BASE_URL}/tx/{txid}"
        response = requests.get(url, timeout=15)
        if response.status_code == 404:
            logger.warning(f"TXID {txid} not found (404). Skipping.")
            return None
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception(f"Failed to get full transaction details for txid {txid}: {e}")
        return None

# In sensora_indexer/src/sensora_indexer/daemon.py
# Add 'threading' to your imports

# --- NEW HEARTBEAT WORKER LOGIC ---
def heartbeat_worker():
    """
    Periodically checks the online status and reputation of all known sensors.
    """
    logger.info("Heartbeat worker thread started.")
    while True:
        try:
            logger.info("Starting heartbeat check cycle...")
            conn = database.get_registry_db_connection()
            sensors_to_check = conn.execute("SELECT device_id, ipv6_address, port FROM sensors").fetchall()
            conn.close()
            
            logger.info(f"Checking status for {len(sensors_to_check)} sensors.")
            
            for sensor in sensors_to_check:
                sensor_dict = dict(sensor)
                device_id = sensor_dict['device_id']
                url = f"http://[{sensor_dict['ipv6_address']}]:{sensor_dict['port']}/status"
                
                try:
                    # Very short timeout, we don't want to wait long for offline sensors
                    response = requests.get(url, timeout=5)
                    response.raise_for_status()
                    data = response.json()
                    
                    # We got a successful response, update the DB with online status and metrics
                    if data.get('status') == 'online':
                        database.update_sensor_reputation(device_id, True, data.get('reputation'))
                    else:
                        database.update_sensor_reputation(device_id, False, None)

                except requests.exceptions.RequestException as e:
                    # Any network error (timeout, connection refused) means it's offline
                    logger.warning(f"Heartbeat failed for sensor {device_id}: {e}")
                    database.update_sensor_reputation(device_id, False, None)

        except Exception as e:
            logger.exception(f"An error occurred in the heartbeat_worker loop: {e}")
        
        # Wait for a long interval before the next full check cycle
        logger.info(f"Heartbeat cycle complete. Next check in {3600} seconds.")
        time.sleep(3600) # Check all sensors once per hour

# In the main() function, start this new thread
def main_loop():
    # ... (the existing main_loop code)
    pass

if __name__ == "__main__":
    logger.info("--- Starting Sensōra Indexer Daemon ---")
    database.init_registry_db()

    # Start the heartbeat worker in its own thread
    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True, name="HeartbeatThread")
    heartbeat_thread.start()
    
    # Start the main block polling loop
    # This will now run in the main thread
    main_loop()

def main_loop():
    """The main polling loop for the indexer daemon."""
    logger.info("--- Starting Sensōra Indexer Daemon (Optimized Polling Mode) ---")
    database.init_registry_db()


    # 1. Get the last processed block from our DB
    last_processed_str = database.get_indexer_state('last_processed_block_height')
    last_processed_height = 0
    if last_processed_str:
        try:
            last_processed_height = int(last_processed_str)
            logger.info(f"Found last processed block height in DB: {last_processed_height}")
            # To handle potential reorgs, re-process the last 15 blocks
            reorg_safety_margin = 15
            last_processed_height = max(0, last_processed_height - reorg_safety_margin)
            logger.info(f"Rolling back {reorg_safety_margin} blocks for safety. Starting scan from block {last_processed_height}.")
        except (ValueError, TypeError):
            logger.warning("Invalid value for 'last_processed_block_height' in DB. Starting from scratch.")
            last_processed_height = 0

    # 2. If DB is empty, start from a recent point in the chain
    if last_processed_height == 0:
        logger.info("No valid last processed block found. Starting from a recent point in the chain.")
        current_height = get_current_block_height()
        if current_height:
            last_processed_height = current_height - config.BACKFILL_BLOCK_COUNT
            logger.info(f"Set starting block height to {last_processed_height}")
        else:
            logger.critical("Could not get current block height. Cannot start. Exiting.")
            sys.exit(1)

    while True:
        try:
            current_height = get_current_block_height()
            if not current_height:
                logger.warning("Could not get current block height. Retrying in 60s.")
                time.sleep(60)
                continue

            if last_processed_height >= current_height:
                logger.info(f"Caught up to current block height ({current_height}). Waiting for new blocks...")
                time.sleep(60)
                continue

            for target_height in range(last_processed_height + 1, current_height + 1):
                logger.info(f"Processing block {target_height}...")
                
                # --- START OPTIMIZATION ---
                # Get only the TXIDs of transactions that have an OP_RETURN
                op_return_txids = get_block_op_return_txs(target_height)
                
                if op_return_txids is not None: # Check for None in case of API error
                    if not op_return_txids:
                        logger.info(f"No transactions with OP_RETURN found in block {target_height}.")
                    else:
                        logger.info(f"Found {len(op_return_txids)} transactions with OP_RETURN in block {target_height}. Fetching details...")
                        for i, txid in enumerate(op_return_txids):
                            logger.debug(f"Processing OP_RETURN tx {i+1}/{len(op_return_txids)}: {txid}")
                            tx_data = get_full_transaction(txid)
                            if tx_data:
                                process_transaction_data(tx_data)
                # --- END OPTIMIZATION ---
                
                last_processed_height = target_height
                database.set_indexer_state('last_processed_block_height', str(last_processed_height))
                logger.info(f"Finished processing block {target_height}. Last processed height is now {last_processed_height}.")

        except KeyboardInterrupt:
            logger.info("Indexer daemon stopped by user.")
            break
        except Exception as e:
            logger.exception(f"An uncaught error occurred in the main loop: {e}. Retrying in 5 minutes...")
            time.sleep(300)

if __name__ == "__main__":
    main_loop()