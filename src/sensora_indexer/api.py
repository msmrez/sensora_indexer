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



@app.route("/api/v1/sensors/search", methods=['GET'])
def search_sensors():
    """
    Searches for sensors, now with sorting by reputation.
    e.g., /search?data_type=1&sort=reputation
    """
    data_type_str = request.args.get('data_type')
    geo_prefix = request.args.get('geo_prefix')
    sort_by = request.args.get('sort', 'timestamp') # Default to timestamp sort

    data_type = int(data_type_str) if data_type_str else None
            
    # The find_sensors function now handles the sorting logic
    sensors = db.find_sensors(data_type=data_type, geo_prefix=geo_prefix, sort_by=sort_by)
    return jsonify(sensors)


@app.route("/", methods=['GET'])
def index_dashboard():
    """Serves the main HTML dashboard page for the registry."""
    # Fetch sensors sorted by reputation for the dashboard
    all_sensors = db.find_sensors(limit=50, sort_by='reputation')
    
    for sensor in all_sensors:
        details = db.get_sensor_details(sensor['device_id'])
        sensor['services_offered'] = details.get('services_offered', []) if details else []

    return render_template(
        "index.html",
        sensors=all_sensors,
        time=time 
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

@app.route("/api/v1/sensor/<string:device_id>/<int:port>", methods=['GET'])
def get_single_sensor(device_id: str, port: int):
    """Gets the detailed profile of a single sensor agent by its ID and port."""
    sensor_profile = db.get_sensor_details(device_id, port) # Pass both to the DB function
    if not sensor_profile:
        abort(404, description=f"Sensor with device_id '{device_id}' on port '{port}' not found.")
    return jsonify(sensor_profile)

def main():
    """Main entry point to run the API server."""
    logger.info("--- Starting Sensōra Registry API Server ---")
    # For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host="::", port=8081, debug=False)

# This block allows running the Flask app directly
if __name__ == "__main__":
    main()