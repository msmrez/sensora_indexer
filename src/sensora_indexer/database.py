# sensora_indexer/database.py

import sqlite3
import logging
from . import config

logger = logging.getLogger(__name__)

def get_registry_db_connection():
    conn = sqlite3.connect(config.REGISTRY_DATABASE_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_registry_db():
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        # Main table to store sensor information
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                device_id TEXT PRIMARY KEY, -- Using IPv6 as the unique ID for now
                ipv6_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                geohash TEXT,
                last_adv_txid TEXT NOT NULL,
                last_adv_timestamp INTEGER NOT NULL,
                first_seen_timestamp INTEGER,
                is_online BOOLEAN DEFAULT 1 -- Assume online until a heartbeat fails
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
        # Simple key-value store for the indexer's own state
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS indexer_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        logger.info("Sensor registry database initialized successfully.")
    except Exception as e:
        logger.exception(f"Failed to initialize registry database: {e}")
    finally:
        if conn:
            conn.close()

def upsert_sensor_advertisement(adv_data: dict):
    """
    Inserts or updates a sensor and its services based on advertisement data.
    This is an atomic operation to ensure data consistency.
    """
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()

        # Use INSERT OR REPLACE to add/update the main sensor entry
        cursor.execute('''
            INSERT INTO sensors (device_id, ipv6_address, port, geohash, last_adv_txid, last_adv_timestamp, first_seen_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                ipv6_address=excluded.ipv6_address,
                port=excluded.port,
                geohash=excluded.geohash,
                last_adv_txid=excluded.last_adv_txid,
                last_adv_timestamp=excluded.last_adv_timestamp,
                is_online=1 -- Mark as online since we just saw an advertisement
        ''', (
            adv_data['device_id'], adv_data['ipv6_address'], adv_data['port'],
            adv_data.get('geohash'), adv_data['txid'], adv_data['timestamp'], adv_data['timestamp']
        ))
        
        # Delete old services for this device to replace them with the new list
        cursor.execute("DELETE FROM services WHERE device_id = ?", (adv_data['device_id'],))
        
        # Insert the new list of services
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
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def get_indexer_state(key: str) -> str | None:
    # ... Function to get values like 'last_processed_block_height'
    pass

def set_indexer_state(key: str, value: str):
    # ... Function to set values like 'last_processed_block_height'
    pass