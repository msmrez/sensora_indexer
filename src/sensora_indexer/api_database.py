# sensora_indexer/src/sensora_indexer/api_database.py

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

def get_sensor_details(device_id: str) -> dict | None:
    """Fetches the full profile of a single sensor, including its services."""
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sensors WHERE device_id = ?", (device_id,))
        sensor_row = cursor.fetchone()
        
        if not sensor_row:
            return None
            
        sensor_profile = dict(sensor_row)
        
        cursor.execute("SELECT data_type_code, price_sats FROM services WHERE device_id = ?", (device_id,))
        service_rows = cursor.fetchall()
        sensor_profile['services_offered'] = [dict(row) for row in service_rows]
            
        return sensor_profile
    except Exception as e:
        logger.exception(f"Error fetching details for sensor {device_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def find_sensors(data_type: int | None = None, geo_prefix: str | None = None, limit: int = 100, sort_by: str = 'timestamp') -> list:
    """
    Finds sensors, with optional filtering and sorting.
    """
    sensors_found = []
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        # --- START CORRECTION: Add reputation columns to the SELECT statement ---
        base_query = "SELECT DISTINCT s.device_id, s.ipv6_address, s.port, s.geohash, s.last_adv_timestamp, s.last_adv_txid, s.is_online, s.uptime_percentage, s.stamp_success_rate, s.total_stamps FROM sensors s"
        # --- END CORRECTION ---

        conditions = ["s.is_online = 1"]
        params = []
        
        if data_type is not None:
            base_query += " JOIN services svc ON s.device_id = svc.device_id"
            conditions.append("svc.data_type_code = ?")
            params.append(data_type)
        
        if geo_prefix:
            conditions.append("s.geohash LIKE ?")
            params.append(f"{geo_prefix}%")
        
        query = base_query
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        # --- Add sorting logic ---
        if sort_by == 'reputation':
            # A simple reputation score: uptime * success rate
            query += " ORDER BY (s.uptime_percentage * s.stamp_success_rate) DESC, s.last_adv_timestamp DESC"
        else: # Default sort by most recently seen
            query += " ORDER BY s.last_adv_timestamp DESC"
        
        query += " LIMIT ?"
        params.append(limit)
        
        logger.debug(f"Executing sensor search query: {query} with params: {tuple(params)}")
        cursor.execute(query, tuple(params))
        
        for row in cursor.fetchall():
            sensors_found.append(dict(row))
            
    except Exception as e:
        logger.exception(f"Error finding sensors with query: {query}")
        return []
    finally:
        if conn:
            conn.close()
            
    return sensors_found
