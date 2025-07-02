# sensora_indexer/src/sensora_indexer/api.py

import logging
import json
from flask import Flask, jsonify, request, abort
from werkzeug.exceptions import HTTPException
# Import our project modules
from . import api_database as db # Use the aliased db for clarity
from . import config

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Flask App Creation ---
app = Flask(__name__)

# --- Error Handlers ---
@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    response = e.get_response()
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response

# --- API Routes ---

@app.route("/api/v1/status", methods=['GET'])
def get_api_status():
    """A simple health check endpoint for the API."""
    return jsonify({"status": "online", "service": "Sensora Registry API"})

@app.route("/api/v1/sensors", methods=['GET'])
def list_all_sensors():
    """Lists all recently active and online sensors."""
    logger.info("API endpoint /api/v1/sensors hit!")
    sensors = db.find_sensors() # This now calls our simplified function
    logger.info(f"Database query returned {len(sensors)} sensors.")
    return jsonify(sensors)

@app.route("/api/v1/sensor/<string:device_id>", methods=['GET'])
def get_single_sensor(device_id: str):
    """Gets the detailed profile of a single sensor by its ID (IPv6 address)."""
    sensor_profile = db.get_sensor_details(device_id)
    if not sensor_profile:
        abort(404, description=f"Sensor with device_id '{device_id}' not found.")
    return jsonify(sensor_profile)

@app.route("/api/v1/sensors/search", methods=['GET'])
def search_sensors():
    """
    Searches for sensors based on query parameters.
    e.g., /search?data_type=1&geo_prefix=u4p
    """
    # Get query parameters
    data_type_str = request.args.get('data_type')
    geo_prefix = request.args.get('geo_prefix')
    
    data_type = None
    if data_type_str:
        try:
            data_type = int(data_type_str)
        except ValueError:
            abort(400, description="Invalid 'data_type' parameter. Must be an integer.")
            
    if not data_type and not geo_prefix:
        abort(400, description="At least one search parameter ('data_type' or 'geo_prefix') is required.")

    sensors = db.find_sensors(data_type=data_type, geo_prefix=geo_prefix)
    return jsonify(sensors)

def main():
    """Main entry point to run the API server."""
    logger.info("--- Starting Sensōra Registry API Server ---")
    # For production, use a proper WSGI server like Gunicorn or Waitress
    # Example: gunicorn -w 4 -b '[::]:8081' 'sensora_indexer.api:app'
    app.run(host="::", port=8081, debug=False)

if __name__ == "__main__":
    main()