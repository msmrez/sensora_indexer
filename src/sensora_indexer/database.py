# sensora_indexer/src/sensora_indexer/database.py

import sqlite3
import logging
from . import config

logger = logging.getLogger(__name__)

def get_registry_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(config.REGISTRY_DATABASE_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"API_DB_ERROR: Could not connect to database '{config.REGISTRY_DATABASE_NAME}': {e}")
        return None

def init_registry_db():
    # ...
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensors (
            device_id TEXT PRIMARY KEY,
            ipv6_address TEXT NOT NULL,
            port INTEGER NOT NULL,
            geohash TEXT,
            last_adv_txid TEXT NOT NULL,
            last_adv_timestamp INTEGER NOT NULL,
            first_seen_timestamp INTEGER,
            is_online BOOLEAN DEFAULT 0,
            -- NEW REPUTATION COLUMNS --
            last_heartbeat_timestamp INTEGER,
            uptime_percentage REAL DEFAULT 0.0,
            stamp_success_rate REAL DEFAULT 0.0,
            total_stamps INTEGER DEFAULT 0
        )
    ''')

def upsert_sensor_advertisement(adv_data: dict):
    # ... (This function is correct and remains unchanged)
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensors (device_id, ipv6_address, port, geohash, last_adv_txid, last_adv_timestamp, first_seen_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                ipv6_address=excluded.ipv6_address,
                port=excluded.port,
                geohash=excluded.geohash,
                last_adv_txid=excluded.last_adv_txid,
                last_adv_timestamp=excluded.last_adv_timestamp,
                is_online=1
        ''', (
            adv_data['device_id'], adv_data['ipv6_address'], adv_data['port'],
            adv_data.get('geohash'), adv_data['txid'], adv_data['timestamp'], adv_data['timestamp']
        ))
        cursor.execute("DELETE FROM services WHERE device_id = ?", (adv_data['device_id'],))
        services_to_insert = []
        for service in adv_data.get('services', []):
            services_to_insert.append((
                adv_data['device_id'],
                service['data_type'],
                service['price_sats']
            ))
        if services_to_insert:
            cursor.executemany(
                "INSERT INTO services (device_id, data_type_code, price_sats) VALUES (?, ?, ?)",
                services_to_insert
            )
        conn.commit()
        logger.info(f"Successfully upserted advertisement for sensor {adv_data['device_id']}")
    except Exception as e:
        logger.exception(f"Failed to upsert sensor advertisement for {adv_data.get('device_id')}: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()


def get_indexer_state(key: str) -> str | None:
    # ... (This function is correct and remains unchanged)
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM indexer_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else None
    except Exception as e:
        logger.exception(f"Error getting state for key '{key}': {e}")
        return None
    finally:
        if conn: conn.close()


def set_indexer_state(key: str, value: str):
    # ... (This function is correct and remains unchanged)
    conn = None
    try:
        conn = get_registry_db_connection()
        conn.execute("INSERT OR REPLACE INTO indexer_state (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    except Exception as e:
        logger.exception(f"Error setting state for key '{key}': {e}")
    finally:
        if conn: conn.close()



# Add this new function to sensora_indexer/src/sensora_indexer/database.py

def update_sensor_reputation(device_id: str, is_online: bool, reputation_data: dict | None):
    """Updates a sensor's online status and reputation metrics."""
    conn = None
    try:
        conn = get_registry_db_connection()
        
        last_heartbeat = int(time.time())
        if is_online and reputation_data:
            # If the sensor responded, update all its metrics
            conn.execute('''
                UPDATE sensors 
                SET is_online = 1, 
                    last_heartbeat_timestamp = ?,
                    uptime_percentage = ?,
                    stamp_success_rate = ?,
                    total_stamps = ?
                WHERE device_id = ?
            ''', (
                last_heartbeat,
                reputation_data.get('uptime_percentage', 0),
                reputation_data.get('stamp_success_rate', 0),
                reputation_data.get('total_stamps_recorded', 0),
                device_id
            ))
        else:
            # If it failed the heartbeat, just mark it as offline
            conn.execute("UPDATE sensors SET is_online = 0 WHERE device_id = ?", (device_id,))
        
        conn.commit()
        logger.info(f"Updated reputation status for {device_id} (Online: {is_online})")
    except Exception as e:
        logger.exception(f"Failed to update sensor reputation for {device_id}: {e}")
    finally:
        if conn:
            conn.close()