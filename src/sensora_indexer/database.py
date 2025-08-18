# sensora_indexer/src/sensora_indexer/database.py

import sqlite3
import logging
import json
from . import config
import os
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

        # UPDATED sensors TABLE SCHEMA
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                device_id TEXT,
                port INTEGER,
                ipv6_address TEXT NOT NULL,
                geohash TEXT,
                last_adv_timestamp INTEGER,
                last_adv_txid TEXT,
                is_online INTEGER DEFAULT 0,
                uptime_percentage REAL DEFAULT 100.0,
                stamp_success_rate REAL DEFAULT 100.0,
                total_stamps INTEGER DEFAULT 0,
                total_advertisements INTEGER DEFAULT 0,
                PRIMARY KEY (device_id, port)
            );
        ''')

        # --- THIS IS THE CRITICAL CHANGE FOR THE SERVICES TABLE ---
        cursor.execute('''
    CREATE TABLE IF NOT EXISTS services (
        device_id TEXT,
        port INTEGER,
        data_type_code INTEGER,
        name TEXT,             -- NEW
        description TEXT,      -- NEW
        units TEXT,            -- NEW
        price_sats INTEGER,
        PRIMARY KEY (device_id, port, data_type_code),
        FOREIGN KEY (device_id, port) REFERENCES sensors (device_id, port) ON DELETE CASCADE
    );
''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS indexer_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
    logger.info("[DB_INIT] Attempting to create table network_stats...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS network_stats (
            stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL UNIQUE,
            online_agents INTEGER NOT NULL,
            total_agents INTEGER NOT NULL,
            new_proofs_in_period INTEGER NOT NULL,
            new_advs_in_period INTEGER NOT NULL
        );
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_network_stats_timestamp ON network_stats (timestamp);
    ''')
    logger.info("[DB_INIT] CREATE TABLE network_stats statement executed.")
    # --- END OF NEW TABLE ---
        conn.commit()
        logger.info("Database initialized successfully with the latest schema.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
    finally:
        if conn:
            conn.close()

# In database.py

def upsert_sensor_advertisement(adv_data: dict):
    """Inserts or updates a sensor's profile, including its rich service data."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        device_id = adv_data['device_id']
        port = adv_data['port']
        
        # This part for the 'sensors' table remains the same
        cursor.execute('''
            INSERT INTO sensors (device_id, port, ipv6_address, geohash, last_adv_timestamp, last_adv_txid, is_online, total_advertisements)
            VALUES (?, ?, ?, ?, ?, ?, 1, 
                COALESCE((SELECT total_advertisements FROM sensors WHERE device_id = ? AND port = ?), 0) + 1
            )
            ON CONFLICT(device_id, port) DO UPDATE SET
                ipv6_address = excluded.ipv6_address,
                geohash = excluded.geohash,
                last_adv_timestamp = excluded.last_adv_timestamp,
                last_adv_txid = excluded.last_adv_txid,
                is_online = 1,
                total_advertisements = sensors.total_advertisements + 1;
        ''', (
            device_id, port, adv_data['ipv6_address'], adv_data['geohash'],
            adv_data['timestamp'], adv_data['txid'],
            device_id, port
        ))
        logger.info(f"Upserting services for {device_id}:{port}. Received services list: {adv_data.get('services')}")
        # --- THIS IS THE NEW LOGIC FOR THE 'services' TABLE ---
        # First, clear old services for this agent to handle service changes.
        cursor.execute("DELETE FROM services WHERE device_id = ? AND port = ?", (device_id, port))

        # Then, insert the new services from the parsed JSON payload.
        for service in adv_data.get('services', []):
            logger.info(f"Processing service item: {service}")
            cursor.execute('''
                INSERT INTO services (device_id, port, data_type_code, name, description, units, price_sats)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id, 
                port, 
                service.get('type'),
                service.get('name'),
                service.get('desc'),
                ','.join(service.get('units', [])), # Store list as comma-separated string
                service.get('price')
            ))
        # --- END OF NEW LOGIC ---

        conn.commit()
        logger.info(f"Successfully upserted rich advertisement for sensor {device_id} on port {port}")
    except Exception as e:
        logger.exception(f"Failed to upsert sensor advertisement for {device_id} on port {port}: {e}")
    finally:
        if conn:
            conn.close()

def update_sensor_reputation(device_id: str, port: int, is_online: bool, reputation_data: dict | None):
    """Updates the online status and reputation metrics for a sensor."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()

        if is_online and reputation_data:
            # Agent is online, update everything
            cursor.execute('''
                UPDATE sensors
                SET is_online = 1,
                    stamp_success_rate = ?,
                    total_stamps = ?,
                    uptime_percentage = ?
                WHERE device_id = ? AND port = ?;
            ''', (
                reputation_data.get('stamp_success_rate', 100.0),
                reputation_data.get('total_stamps_recorded', 0),
                reputation_data.get('uptime_percentage', 100.0),
                device_id,
                port
            ))
            logger.info(f"Updated reputation for ONLINE sensor {device_id}:{port}")
        else:
            # Agent is offline, mark it as such
            cursor.execute("UPDATE sensors SET is_online = 0 WHERE device_id = ? AND port = ?", (device_id, port))
            logger.warning(f"Marked sensor {device_id}:{port} as OFFLINE.")
        
        conn.commit()
    except Exception as e:
        logger.exception(f"Failed to update reputation for sensor {device_id}:{port}: {e}")
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



def get_current_network_stats(last_stat_timestamp: int = 0) -> dict:
    """
    Calculates the current state of the network by querying the sensors table.
    """
    conn = get_registry_db_connection()
    cursor = conn.cursor()
    
    # Get total and online agent counts
    cursor.execute("SELECT COUNT(*) FROM sensors")
    total_agents = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sensors WHERE is_online = 1")
    online_agents = cursor.fetchone()[0]
    
    # This is a placeholder for now, as the indexer doesn't track proofs.
    # A more advanced version would have the indexer also watch for SENSORA_PROOF txs.
    new_proofs_since_last = 0 

    # Get the distribution of services
    cursor.execute("""
        SELECT s.name, COUNT(*) as count 
        FROM services s
        JOIN sensors sen ON s.device_id = sen.device_id AND s.port = sen.port
        WHERE sen.is_online = 1
        GROUP BY s.name
        ORDER BY count DESC
    """)
    service_rows = cursor.fetchall()
    service_distribution = {row['name']: row['count'] for row in service_rows}

    conn.close()
    
    return {
        "timestamp": int(time.time()),
        "online_agents": online_agents,
        "total_agents": total_agents,
        "new_proofs_since_last": new_proofs_since_last,
        "service_distribution": json.dumps(service_distribution) # Store as a JSON string
    }

def save_network_stats(stats: dict):
    """
    Saves a snapshot of network statistics to the database.
    """
    conn = get_registry_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO network_stats 
            (timestamp, online_agents, total_agents, new_proofs_since_last, service_distribution)
            VALUES (?, ?, ?, ?, ?)
        """, (
            stats['timestamp'],
            stats['online_agents'],
            stats['total_agents'],
            stats['new_proofs_since_last'],
            stats['service_distribution']
        ))
        conn.commit()
        logger.info(f"Successfully saved network stats for timestamp {stats['timestamp']}.")
    except sqlite3.IntegrityError:
        logger.warning("Network stats for this timestamp already exist. Skipping.")
    except Exception as e:
        logger.exception("Failed to save network stats.")
    finally:
        if conn:
            conn.close()