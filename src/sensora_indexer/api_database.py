# sensora_indexer/src/sensora_indexer/api_database.py

import sqlite3
import logging
from . import config

logger = logging.getLogger(__name__)

def get_registry_db_connection():
    """Establishes a connection to the SQLite database."""
    # This is a read-only connection, but we use the same helper
    try:
        conn = sqlite3.connect(config.REGISTRY_DATABASE_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"API_DB_ERROR: Could not connect to database '{config.DATABASE_NAME}': {e}")
        return None

def get_sensor_details(device_id: str) -> dict | None:
    """Fetches the full profile of a single sensor, including its services."""
    sensor_profile = None
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        # Get main sensor info
        cursor.execute("SELECT * FROM sensors WHERE device_id = ?", (device_id,))
        sensor_row = cursor.fetchone()
        
        if sensor_row:
            sensor_profile = dict(sensor_row)
            
            # Get associated services
            cursor.execute("SELECT data_type_code, price_sats FROM services WHERE device_id = ?", (device_id,))
            service_rows = cursor.fetchall()
            sensor_profile['services_offered'] = [dict(row) for row in service_rows]
            
    except Exception as e:
        logger.exception(f"Error fetching details for sensor {device_id}: {e}")
        return None # Return None on error
    finally:
        if conn:
            conn.close()
            
    return sensor_profile

def find_sensors(data_type: int | None = None, geo_prefix: str | None = None, limit: int = 100) -> list:
    """Finds sensors, optionally filtering by data_type and/or geohash prefix."""
    sensors_found = []
    conn = None
    try:
        conn = get_registry_db_connection()
        cursor = conn.cursor()
        
        # Build the query dynamically
        query = "SELECT s.* FROM sensors s"
        params = []
        conditions = []
        
        if data_type is not None:
            # Join with services table to filter by data_type
            query += " JOIN services svc ON s.device_id = svc.device_id"
            conditions.append("svc.data_type_code = ?")
            params.append(data_type)
        
        if geo_prefix:
            conditions.append("s.geohash LIKE ?")
            params.append(f"{geo_prefix}%") # Use LIKE for prefix search
            
        # Always filter for online sensors
        conditions.append("s.is_online = 1")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY s.last_adv_timestamp DESC LIMIT ?"
        params.append(limit)
        
        logger.debug(f"Executing sensor search query: {query} with params: {params}")
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            sensors_found.append(dict(row))
            
    except Exception as e:
        logger.exception(f"Error finding sensors: {e}")
        return [] # Return empty list on error
    finally:
        if conn:
            conn.close()
            
    return sensors_found