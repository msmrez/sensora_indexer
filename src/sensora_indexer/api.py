# sensora_indexer/src/sensora_indexer/api.py

import logging
import json
import time
from flask import Flask, jsonify, request, abort, render_template
from werkzeug.exceptions import HTTPException

# Import our project modules
from . import api_database as db
from . import config

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Flask App Creation ---
# The template_folder is specified relative to the app's root path.
# When run as a module, this should resolve correctly if templates is in the same dir as api.py's package.
# A more robust way is to set it relative to the app's instance path.
app = Flask(__name__, template_folder='templates')


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


# --- HTML Dashboard Route ---
@app.route("/", methods=['GET'])
def index_dashboard():
    """Serves the main HTML dashboard page for the registry."""
    logger.info("Request received for index dashboard.")
    all_sensors = []
    try:
        # Fetch latest 50 sensors to display
        all_sensors = db.find_sensors(limit=50) 
        
        # For each sensor, get its detailed services list
        for sensor in all_sensors:
            details = db.get_sensor_details(sensor['device_id'])
            sensor['services_offered'] = details.get('services_offered', []) if details else []

    except Exception as e:
        logger.exception("Error preparing data for dashboard.")

    return render_template(
        "index.html",
        sensors=all_sensors,
        time=time # Pass time module for formatting timestamps in the template
    )

# --- API Routes ---

@app.route("/api/v1/status", methods=['GET'])
def get_api_status():
    """A simple health check endpoint for the API."""
    return jsonify({"status": "online", "service": "Sensora Registry API"})

@app.route("/api/v1/sensors", methods=['GET'])
def list_all_sensors():
    """Lists all recently active and online sensors."""
    sensors = db.find_sensors()
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
    app.run(host="::", port=8081, debug=False)

# This block allows running the Flask app directly
if __name__ == "__main__":
    main()