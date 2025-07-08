import os

# --- PROJECT ROOT ---
# This finds the root directory of the project (e.g., /root/sensora-indexer/)
# It assumes the src directory is in the project root.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- DATABASE ---
# Define the database path relative to the project root.
REGISTRY_DATABASE_NAME = os.path.join(PROJECT_ROOT, "sensor_registry.db")

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
REWIND_ON_STARTUP = 15
# When scanning a block, check any untagged transaction smaller than this size (in bytes)
# just in case its 'op_return' tag was missed by the API. Our SNSRADV1 tx is ~255 bytes.
