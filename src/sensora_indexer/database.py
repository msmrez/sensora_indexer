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
    """Initializes the database and creates all necessary tables."""
    conn = None
    try:
        conn = get_registry_db_connection()
        if not conn:
            raise sqlite3.Error("Failed to get DB connection for initialization.")
            
        cursor = conn.cursor()
        # Main table to store sensor information
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                device_id TEXT PRIMARY KEY, 
                ipv6_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                geohash TEXT,
                last_adv_txid TEXT NOT NULL,
                last_adv_timestamp INTEGER NOT NULL,
                first_seen_timestamp INTEGER,
                is_online BOOLEAN DEFAULT 1
            )
        ''')
        # Table to store the services/data types offered by each sensor
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                service_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                data_type_code INTEGER NOT NULL,
                price_sats INTEGER NOT NULL,
                FOREIGN KEY (device_id) REFERENCES sensors (device_id) ON DELETE CASCADE
            )
        ''')
        
        # --- START FIX: ADD THE MISSING TABLE ---
        # Simple key-value store for the indexer's own state
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS indexer_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # --- END FIX ---
        
        conn.commit()
        logger.info("Sensor registry database initialized successfully.")
    except Exception as e:
        logger.exception(f"Failed to initialize registry database: {e}")
    finally:
        if conn:
            conn.close()

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