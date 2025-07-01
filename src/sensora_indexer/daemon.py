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

def get_current_block_height() -> int | None:
    """Fetches the current block height from the blockchain info endpoint."""
    try:
        url = f"{config.BITAILS_API_BASE_URL}/blockchain/info"
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

def main_loop():
    """The main polling loop for the indexer daemon."""
    logger.info("--- Starting Sensōra Indexer Daemon (Polling Mode) ---")
    database.init_registry_db()

    last_processed_str = database.get_indexer_state('last_processed_block_height')
    last_processed_height = int(last_processed_str) if last_processed_str else 0

    if last_processed_height == 0:
        logger.info("No last processed block found. Starting from recent history.")
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
                time.sleep(60) # Wait for a minute before checking again
                continue

            # Process blocks from the last known height up to the current height
            for target_height in range(last_processed_height + 1, current_height + 1):
                logger.info(f"Processing block {target_height}...")
                
                txids = get_block_txids(target_height)
                if txids:
                    logger.info(f"Found {len(txids)} transactions in block {target_height}.")
                    for i, txid in enumerate(txids):
                        logger.debug(f"Processing tx {i+1}/{len(txids)}: {txid}")
                        tx_data = get_full_transaction(txid)
                        if tx_data:
                            process_transaction_data(tx_data)
                
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