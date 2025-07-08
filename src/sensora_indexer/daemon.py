# src/sensora_indexer/daemon.py

import json
import logging
import time
import requests
import sys
import threading

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
        if not script_hex or not (script_hex.startswith("006a") or script_hex.startswith("6a")):
            continue
        
        # --- START FINAL CORRECTION ---
        # 1. Parse the entire OP_RETURN payload from the script hex.
        op_return_payload = protocols.parse_op_return_from_script_hex(script_hex)
        if not op_return_payload:
            continue

        # 2. Pass this single byte string to the advertisement parser.
        adv_data = protocols.parse_advertisement_payload(op_return_payload)
        if adv_data:
            logger.info(f"Advertisement VERIFIED! TXID: {txid}, Sensor: {adv_data.get('device_id')}")
            adv_data['txid'] = txid
            database.upsert_sensor_advertisement(adv_data)
            return # Stop processing this transaction
        # --- END FINAL CORRECTION ---

def get_current_block_height() -> int | None:
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

def get_block_op_return_txs(height: int) -> list[str] | None:
    try:
        url = f"{config.BITAILS_API_BASE_URL}/block/height/{height}"
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        data = response.json()
        op_return_txs = []
        if 'transactionsDetails' in data and isinstance(data['transactionsDetails'], list):
            for tx_detail in data['transactionsDetails']:
                if 'op_return' in tx_detail.get('tags', []):
                    if tx_detail.get('txid'):
                        op_return_txs.append(tx_detail.get('txid'))
            return op_return_txs
        logger.error(f"Could not find 'transactionsDetails' list in block response for height {height}")
        return None
    except Exception as e:
        logger.exception(f"Failed to get and filter block content for height {height}: {e}")
        return None

def get_block_hash(height: int) -> str | None:
    """Gets the hash of a block at a specific height."""
    try:
        url = f"{config.BITAILS_API_BASE_URL}/block/height/{height}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if 'hash' in data:
            return data['hash']
        logger.error(f"Could not find 'hash' in block response for height {height}")
        return None
    except Exception as e:
        logger.exception(f"Failed to get block hash for height {height}: {e}")
        return None

# We keep this function as our reliable way to get full tx details.
def get_full_transaction(txid: str) -> dict | None:
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

def heartbeat_worker():
    logger.info("Heartbeat worker thread started.")
    while True:
        try:
            logger.info("Starting heartbeat check cycle...")
            conn = database.get_registry_db_connection()
            if not conn:
                logger.error("Heartbeat worker could not get DB connection. Retrying later.")
                time.sleep(60); continue
            sensors_to_check = conn.execute("SELECT device_id, ipv6_address, port FROM sensors").fetchall()
            conn.close()
            logger.info(f"Checking status for {len(sensors_to_check)} sensors.")
            for sensor in sensors_to_check:
                sensor_dict = dict(sensor)
                device_id = sensor_dict['device_id']
                url = f"http://[{sensor_dict['ipv6_address']}]:{sensor_dict['port']}/status"
                try:
                    response = requests.get(url, timeout=5)
                    response.raise_for_status()
                    data = response.json()
                    if data.get('status') == 'online':
                        database.update_sensor_reputation(device_id, True, data.get('reputation'))
                    else:
                        database.update_sensor_reputation(device_id, False, None)
                except requests.exceptions.RequestException:
                    logger.warning(f"Heartbeat failed for sensor {device_id} (network error/timeout).")
                    database.update_sensor_reputation(device_id, False, None)
        except Exception as e:
            logger.exception(f"An error occurred in the heartbeat_worker loop: {e}")
        logger.info(f"Heartbeat cycle complete. Next check in 1 hour.")
        time.sleep(3600)
        

def block_polling_loop():
    logger.info("Block polling loop started.")
    last_processed_str = database.get_indexer_state('last_processed_block_height')
    last_processed_height = int(last_processed_str) if last_processed_str else 0

    # ... (the startup/rewind logic is the same)
    if last_processed_height > 0:
        logger.info(f"Restart detected. Last processed block was {last_processed_height}.")
        rewind_amount = config.REWIND_ON_STARTUP
        last_processed_height = max(0, last_processed_height - rewind_amount)
        logger.info(f"Rewinding {rewind_amount} blocks. New starting height: {last_processed_height}")
    else:
        # This is the very first run.
        logger.info("No last processed block found. Starting from recent history.")
        current_height = get_current_block_height()
        if current_height:
            last_processed_height = max(0, current_height - config.BACKFILL_BLOCK_COUNT)
            logger.info(f"Set starting block height to {last_processed_height}")
        else:
            logger.critical("Could not get current block height. Cannot start polling loop.")
            return

    while True:
        try:
            current_height = get_current_block_height()
            if not current_height:
                time.sleep(60); continue
            if last_processed_height >= current_height:
                time.sleep(60); continue

            for target_height in range(last_processed_height + 1, current_height + 1):
                logger.info(f"Processing block {target_height}...")
                
                # Step 1: Get the block hash for the target height.
                block_hash = get_block_hash(target_height)
                if not block_hash:
                    logger.error(f"Could not get block hash for height {target_height}. Skipping block.")
                    continue
                candidate_txids = set()
                total_tx_count = 0
                
                current_pos = 0
                limit = 200 # Can use a slightly larger limit now

                logger.info(f"Fetching transaction list for block {target_height}...")
                while True:
                    url = f"{config.BITAILS_API_BASE_URL}/block/{block_hash}/transactions?from={current_pos}&limit={limit}"
                    try:
                        response = requests.get(url, timeout=20)
                        response.raise_for_status()
                        tx_summaries = response.json()
                        
                        if not tx_summaries: break
                        
                        total_tx_count += len(tx_summaries)

                        for summary in tx_summaries:
                            # Condition 1: The transaction is explicitly tagged.
                            if 'op_return' in summary.get('tags', []):
                                candidate_txids.add(summary['txid'])
                            # Condition 2 (Our Safety Net): The transaction is small enough to be a candidate.
                            elif summary.get('size', 9999) < config.HEURISTIC_SIZE_THRESHOLD:
                                candidate_txids.add(summary['txid'])
                        
                        current_pos += len(tx_summaries)
                    except Exception as e:
                        logger.exception(f"Error fetching TX list from {url}: {e}")
                        break

                logger.info(f"Scanned {total_tx_count} total transactions. Found {len(candidate_txids)} candidates to check fully.")

                # Now, only fetch the full data for our small list of candidates.
                for txid in candidate_txids:
                    full_tx_data = get_full_transaction(txid)
                    if full_tx_data:
                        process_transaction_data(full_tx_data)

                # --- END MODIFICATION ---
                
                last_processed_height = target_height
                database.set_indexer_state('last_processed_block_height', str(last_processed_height))
                logger.info(f"Finished processing block {target_height}.")
        except Exception as e:
            logger.exception(f"An uncaught error occurred in the block polling loop: {e}. Retrying in 5 minutes...")
            time.sleep(300)
if __name__ == "__main__":
    logger.info("--- Starting Sensōra Indexer Daemon ---")
    database.init_registry_db()

    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True, name="HeartbeatThread")
    heartbeat_thread.start()
    
    try:
        block_polling_loop()
    except KeyboardInterrupt:
        logger.info("Indexer daemon stopped by user.")
    except Exception as e:
        logger.exception(f"Indexer daemon crashed: {e}")