# sensora_indexer/src/sensora_indexer/database.py

import sqlite3
import logging
import json
from . import config

logger = logging.getLogger(__name__)

def get_registry_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        # --- ADD THIS DIAGNOSTIC LINE ---
        db_path = os.path.abspath(config.REGISTRY_DATABASE_NAME)
        logger.info(f"Attempting to connect to DB at absolute path: {db_path}")
        # --- END DIAGNOSTIC LINE ---

        conn = sqlite3.connect(config.REGISTRY_DATABASE_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"DB_ERROR: Could not connect to database '{config.REGISTRY_DATABASE_NAME}': {e}")
        return None
        
def init_registry_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = None
    try:
        conn = get_registry_db_connection()
        if not conn: return

        cursor = conn.cursor()

        # --- THIS IS THE CORRECTED SENSORS TABLE SCHEMA ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                device_id TEXT PRIMARY KEY,
                ipv6_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                geohash TEXT,
                last_adv_timestamp INTEGER,
                last_adv_txid TEXT,
                is_online INTEGER DEFAULT 0,
                -- New Reputation Columns --
                uptime_percentage REAL DEFAULT 100.0,
                stamp_success_rate REAL DEFAULT 100.0,
                total_stamps INTEGER DEFAULT 0,
                total_advertisements INTEGER DEFAULT 0
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                device_id TEXT,
                data_type_code INTEGER,
                price_sats INTEGER,
                PRIMARY KEY (device_id, data_type_code),
                FOREIGN KEY (device_id) REFERENCES sensors (device_id) ON DELETE CASCADE
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS indexer_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')

        conn.commit()
        logger.info("Database initialized successfully with the latest schema.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
    finally:
        if conn:
            conn.close()

def upsert_sensor_advertisement(adv_data: dict):
    """Inserts or updates a sensor's profile based on a new advertisement."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        device_id = adv_data['device_id']
        
        # Upsert into the main sensors table
        cursor.execute('''
            INSERT INTO sensors (device_id, ipv6_address, port, geohash, last_adv_timestamp, last_adv_txid, is_online, total_advertisements)
            VALUES (?, ?, ?, ?, ?, ?, 1, COALESCE((SELECT total_advertisements FROM sensors WHERE device_id = ?), 0) + 1)
            ON CONFLICT(device_id) DO UPDATE SET
                ipv6_address = excluded.ipv6_address,
                port = excluded.port,
                geohash = excluded.geohash,
                last_adv_timestamp = excluded.last_adv_timestamp,
                last_adv_txid = excluded.last_adv_txid,
                is_online = 1,
                total_advertisements = sensors.total_advertisements + 1;
        ''', (
            device_id, adv_data['ipv6_address'], adv_data['port'], adv_data['geohash'],
            adv_data['timestamp'], adv_data['txid'], device_id
        ))

        # Upsert services offered
        for service in adv_data.get('services', []):
            cursor.execute('''
                INSERT INTO services (device_id, data_type_code, price_sats)
                VALUES (?, ?, ?)
                ON CONFLICT(device_id, data_type_code) DO UPDATE SET
                    price_sats = excluded.price_sats;
            ''', (device_id, service['data_type'], service['price_sats']))

        conn.commit()
        logger.info(f"Successfully upserted advertisement for sensor {device_id}")
    except Exception as e:
        logger.exception(f"Failed to upsert sensor advertisement for {adv_data.get('device_id')}: {e}")
    finally:
        if conn:
            conn.close()

def update_sensor_reputation(device_id: str, is_online: bool, reputation_data: dict | None):
    """Updates the online status and reputation metrics for a sensor."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()

        if is_online and reputation_data:
            cursor.execute('''
                UPDATE sensors
                SET is_online = 1,
                    stamp_success_rate = ?,
                    total_stamps = ?
                WHERE device_id = ?;
            ''', (
                reputation_data.get('stamp_success_rate', 100.0),
                reputation_data.get('total_stamps', 0),
                device_id
            ))
        else:
            cursor.execute("UPDATE sensors SET is_online = 0 WHERE device_id = ?", (device_id,))
        
        conn.commit()
    except Exception as e:
        logger.exception(f"Failed to update reputation for sensor {device_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_indexer_state(key: str) -> str | None:
    """Gets a value from the state table."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM indexer_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else None
    finally:
        if conn:
            conn.close()

def set_indexer_state(key: str, value: str):
    """Sets a value in the state table."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO indexer_state (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        if conn:
            conn.close()