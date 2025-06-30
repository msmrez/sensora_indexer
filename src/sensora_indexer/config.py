# src/sensora_indexer/config.py

# --- DATABASE ---
REGISTRY_DATABASE_NAME = "sensor_registry.db"

# --- BITAILS API ---
# CORRECTED: Use wss:// for WebSocket connections
BITAILS_WEBSOCKET_URL = "wss://api.bitails.io/global"
BITAILS_API_BASE_URL = "https://api.bitails.io"

# --- PROTOCOL ---
# The prefix we are looking for in OP_RETURN data
ADVERTISEMENT_PREFIX = b'SNSRADV1'

# --- DAEMON SETTINGS ---
# How far back to check for missed blocks on startup
BACKFILL_BLOCK_COUNT = 144 # e.g., about 1 day worth of blocks