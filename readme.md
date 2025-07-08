# Sensōra Indexer & Registry

This repository contains the **Sensōra Indexer**, a backend service that listens to the BSV blockchain to discover and catalog active IoT data sensors from the **Sensōra Network**.

It consists of two main components:

1.  **The Daemon:** A continuously running process that polls the blockchain, finds `SENSORA_ADV1` advertisement transactions, parses them, and stores the sensor profiles in a database.
2.  **The API:** A Flask-based REST API that serves the collected sensor data, providing a searchable, public registry of all known sensors.

This service is the discovery layer for the Sensōra ecosystem, enabling consumer applications to find data providers.

### The Sensōra Ecosystem

The Indexer is the central discovery layer of the network, acting as the "yellow pages" for available sensors.

```
┌─────────────────┐   1. Advertise Service   ┌────────────────┐   4. Discover Agent   ┌──────────────┐
│  Sensōra Agent  │  ─────────────────────>  │                │  <───────────────────  │              │
│                 │                          │ BSV Blockchain │                        │ Sensōra      │
│ on IoT Device   │   2. Stamp Data Proof    │                │   5. Purchase Data     │ Client       │
│                 │  <─────────────────────  │ (Ledger)       │  ───────────────────>  │              │
└─────────────────┘   3. Listen for Ads      └────────────────┘                        └──────────────┘
       ^            <─────────────────────                          ^
       │                                  │                         │
       │ 6. Query for Agents              │ 3a. Index results       │
       │                                  │                         │
       └───────────────────────────────────[ Sensōra Indexer ]───────┘
```

This service discovers [Sensōra Agents](https://github.com/msmrez/sensora_agent) and provides data for the [Sensōra Client](https://github.com/msmrez/sensora_client).

## Core Features

- **Blockchain-Powered Discovery:** Uses on-chain `OP_RETURN` data (`SENSORA_ADV1` protocol) as the single source of truth.
- **Stateful & Resilient:** Uses a local SQLite database (`sensor_registry.db`) to save its progress, allowing it to stop and restart without losing data or re-scanning the entire blockchain.
- **Robust & Efficient Polling:** Intelligently paginates through block transactions to ensure no advertisements are missed, even on unreliable APIs.
- **Public API:** Exposes the registry via a simple, clean REST API for any developer or application to use.
- **Web Dashboard:** Provides a simple "waterfall" view of all discovered sensors, making the network's status visible to everyone.

## On-Chain Protocol

The Indexer **consumes** the `SENSORA_ADV1` protocol to learn about active sensors.

- **Prefix:** `SENSORA_ADV1` (ASCII)
- **Payload Structure:**

| Field           | Size (Bytes) | Data Type               | Description                         |
| :-------------- | :----------- | :---------------------- | :---------------------------------- |
| Prefix          | **12**       | ASCII                   | `SENSORA_ADV1`                      |
| Device ID Type  | 1            | Unsigned Byte           | `0x01` for Full IPv6                |
| Device ID       | 16           | Bytes                   | The sensor's IPv6 address           |
| Port            | 2            | Unsigned Short (BE)     | API listener port                   |
| Geohash Length  | 1            | Unsigned Byte           | Length of the Geohash string        |
| Geohash         | (variable)   | ASCII                   | Sensor's location                   |
| # of Services   | 1            | Unsigned Byte           | Number of data types offered        |
| Service 1 Type  | 2            | Unsigned Short (BE)     | Code for the service                |
| Service 1 Price | 4            | Unsigned Int (BE)       | Price in satoshis                   |
| ...             | ...          | ...                     | _(Repeat for more services)_        |
| Timestamp       | 8            | Unsigned Long Long (BE) | Unix timestamp of the advertisement |

## How It Works

The indexer daemon operates in a continuous loop:

1.  **Get Current Block Height:** It checks the latest block height on the BSV network.
2.  **Get Block Hash:** For each new block, it retrieves the block's hash.
3.  **Paginate Transactions:** It uses the Bitails API's paginated endpoint to fetch a complete list of all transaction summaries in the block.
4.  **Filter for OP_RETURNs:** It scans the summaries and identifies all transactions tagged with `sensora`.
5.  **Fetch & Parse:** It fetches the full details for only the `sensora` candidate transactions. It looks for the `SENSORA_ADV1` prefix in the `OP_RETURN` data.
6.  **Upsert to Database:** When a valid advertisement is found, it is parsed, and the sensor's information (IPv6, port, services, price, location) is inserted or updated in the `sensor_registry.db`.
7.  **Save State:** After each block is processed, the daemon saves the block height to its database so it knows where to resume on restart.

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

2.  **Set up Virtual Environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Install Daemon and API services:**
    ```bash
    pip install -e .
    ```

### Running the Service

The indexer is a two-part service that should be run in separate terminals or as separate system services (e.g., using `systemd`).

1.  **Run the Indexer Daemon:**
    This process listens to the blockchain and populates the database. It must be running for the API to have any data.

    ```bash
    # From the project root, with venv active
    python -m sensora_indexer.daemon
    ```

    On first run, it will start scanning from a recent block and work its way forward. On restart, it will automatically rewind a few blocks to ensure consistency.

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
