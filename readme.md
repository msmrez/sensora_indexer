# Sensōra Indexer & Registry

This repository contains the **Sensōra Indexer**, a backend service that listens to the BSV blockchain to discover and catalog active IoT data sensors from the **Sensōra Network**.

It consists of two main components:

1.  **The Daemon:** A continuously running process that polls the blockchain, finds `SNSRADV1` advertisement transactions, parses them, and stores the sensor profiles in a database.
2.  **The API:** A Flask-based REST API that serves the collected sensor data, providing a searchable, public registry of all known sensors.

This service is the discovery layer for the Sensōra ecosystem, enabling consumer applications to find data providers. It relies on sensor data broadcast by the [Sensōra Agent](https://github.com/msmrez/sensor_agent) (<- **UPDATE THIS LINK**).

## Core Features

- **Blockchain-Powered Discovery:** Uses on-chain `OP_RETURN` data (`SNSRADV1` protocol) as the single source of truth for sensor advertisements.
- **Stateful & Resilient:** Uses a local SQLite database to save its progress, allowing it to stop and restart without losing data or re-scanning the entire blockchain.
- **Efficient Polling:** Intelligently filters blocks to only process transactions that contain an `OP_RETURN`, drastically reducing API calls and processing load.
- **Public API:** Exposes the registry via a simple, clean REST API for any developer or application to use.
- **Web Dashboard:** Provides a simple "waterfall" view of all discovered sensors, making the network's status visible to everyone.

## How It Works

The indexer operates in a continuous loop:

1.  **Get Current Block Height:** It checks the latest block height on the BSV network via the `bitails.io` API.
2.  **Process New Blocks:** It processes each block it hasn't seen before.
3.  **Filter for OP_RETURNs:** For each block, it gets a list of all transactions that are tagged as containing an `OP_RETURN`.
4.  **Fetch & Parse:** It fetches the full details for only those transactions. It looks for the `SNSRADV1` prefix in the OP_RETURN data.
5.  **Upsert to Database:** When a valid advertisement is found, it is parsed, and the sensor's information (IPv6, port, services, price, location) is inserted or updated in the `sensor_registry.db`.
6.  **Save State:** After each block is processed, the daemon saves the block height to its database so it knows where to resume on restart.
7.  **Serve Data:** The separate API application reads from this same database to serve discovery requests from clients.

## Getting Started

### Prerequisites

- A Linux-based server (e.g., a cloud VM) with Python 3.10+.
- An internet connection.

### Installation

1.  **Clone the Repository:**

    ```bash
    git clone https://github.com/msmrez/sensora_indexer.git
    cd sensora_indexer
    ```

2.  **Set up as an Editable Package:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -e .
    ```

### Running the Service

The indexer is a two-part service that should be run in separate terminals or as separate system services.

1.  **Run the Indexer Daemon:**
    This process listens to the blockchain and populates the database.

    ```bash
    # From the project root, with venv active
    python -m sensora_indexer.daemon
    ```

    On first run, it will start scanning from a recent block and work its way forward.

2.  **Run the Registry API:**
    This process serves the data collected by the daemon.
    ```bash
    # From the project root, in a NEW terminal, with venv active
    python -m sensora_indexer.api
    ```
    The API will be available on port `8081`. You can access the dashboard at `http://YOUR_SERVER_IP:8081/`.

## API Endpoints

- `GET /`: A simple web dashboard showing all discovered sensors.
- `GET /api/v1/sensors`: A JSON list of all registered sensors.
- `GET /api/v1/sensors/search?data_type=...&geo_prefix=...`: A JSON list of sensors filtered by data type and/or geohash.
- `GET /api/v1/sensor/<device_id>`: The detailed profile of a single sensor.

---

_This service is the backbone of the Sensōra network. Future work includes adding the Sensor Reputation system to the API and dashboard._
