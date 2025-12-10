# Standalone Compute Worker

This directory contains a standalone worker that can be deployed independently from the API service. The worker processes jobs from the merged media_store database using Write-Ahead Logging (WAL) mode for safe concurrent multi-process access.

## Structure

```
worker/
  ├── src/
  │   ├── worker.py           # Main worker logic
  │   ├── shared.py           # Shared utilities (models, config, broadcaster)
  │   └── __init__.py
  ├── compute_modules/        # Compute modules with subprocess runners
  │   ├── image_resize/
  │   │   ├── src/runner.py   # Subprocess runner with WAL support
  │   │   └── ...
  │   └── image_conversion/
  │       ├── src/runner.py   # Subprocess runner with WAL support
  │       └── ...
  ├── pyproject.toml          # Dependencies
  ├── start_worker.sh         # Startup script
  └── README.md               # This file
```

## Dependencies

The worker requires:
- `sqlalchemy>=2.0.0` - Database access with WAL support
- `paho-mqtt>=1.6.0` - Event broadcasting
- `cl-server-shared` - Shared configuration, models, and MQTT utilities
- `cl_ml_tools` - Job processing engine and task plugins

## Database Configuration

The worker uses the **merged `media_store.db`** database (formerly separate `compute.db`). All database connections automatically enable **Write-Ahead Logging (WAL)** mode for safe concurrent access by multiple worker processes.

### Database Access Pattern

- **Main Worker**: Polls database for pending jobs, claims them atomically, spawns subprocess runners
- **Subprocess Runners**: Update job status and write results back to database
- **Concurrent Access**: WAL mode allows multiple readers + single writer, preventing database locks

## Usage

### 1. Set Environment Variables

```bash
export CL_SERVER_DIR=/path/to/data  # Shared data directory (must contain media_store.db)
```

**Optional**: Override database URL
```bash
export DATABASE_URL=sqlite:////custom/path/media_store.db
```

### 2. Start the Worker

```bash
cd worker
./start_worker.sh --worker-id worker-1 --tasks image_resize,image_conversion
```

### 3. Or Run Directly with Python

```bash
cd worker
python worker.py --worker-id worker-1 --tasks image_resize
```

## How It Works

1. **Module Discovery**: The worker scans `compute_modules/` for available task modules
2. **Virtual Environments**: Creates isolated venvs for each module on first run
3. **Job Processing**: Polls the shared database for pending jobs and executes them using module-specific runners
4. **WAL Mode**: All database connections (main worker + subprocess runners) automatically enable WAL mode
5. **Independence**: The worker is completely independent from the API service - it only shares the database

## WAL Mode (Write-Ahead Logging)

WAL mode enables safe concurrent database access:
- **Multiple Readers**: Subprocess runners can read database while main worker writes
- **Single Writer**: Only one process writes at a time (atomically claims jobs)
- **No Lock Contention**: WAL creates separate `.db-wal` and `.db-shm` files
- **Automatic**: Enabled on first connection via event listeners in worker and runner code

### WAL Files

The database creates three files:
- `media_store.db` - Main database file
- `media_store.db-wal` - Write-Ahead Log (created automatically)
- `media_store.db-shm` - Shared memory file (created automatically)

These are automatically managed by SQLite and should **not be deleted** while the database is in use.

## MQTT Configuration

The worker uses MQTT for real-time event broadcasting and worker capability announcements.

### MQTT Broker Configuration

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | `localhost` | MQTT broker hostname or IP address |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC` | `inference/events` | Base topic for job progress events |
| `BROADCAST_TYPE` | `mqtt` | Broadcaster type (`mqtt` or `noop` for testing) |

**Example Configuration:**

```bash
# Connect to external MQTT broker
export MQTT_BROKER=mqtt.example.com
export MQTT_PORT=1883

# Or use local broker (default)
export MQTT_BROKER=localhost
export MQTT_PORT=1883

# Disable MQTT broadcasting (for testing)
export BROADCAST_TYPE=noop
```

### MQTT Topics and Message Formats

#### 1. Worker Capability Topic

**Topic Pattern:** `inference/workers/{worker_id}`

**Purpose:** Announces worker availability and capabilities with retained messages

**Message Format:**
```json
{
  "id": "worker-1",
  "capabilities": ["image_resize", "image_conversion"],
  "idle_count": 1,
  "timestamp": 1702123456789
}
```

**Fields:**
- `id` (string): Unique worker identifier
- `capabilities` (array): List of task types this worker can handle
- `idle_count` (integer): 1 when idle, 0 when busy processing a job
- `timestamp` (integer): Unix timestamp in milliseconds

**Behavior:**
- Published as **retained message** when worker starts
- Updated periodically via heartbeat (every 30 seconds by default)
- **Cleared on graceful shutdown** to prevent stale worker registrations
- Cleared via Last Will & Testament (LWT) on unexpected disconnect

**Environment Variables:**
- `CAPABILITY_TOPIC_PREFIX`: Override base topic (default: `inference/workers`)
- `MQTT_HEARTBEAT_INTERVAL`: Heartbeat interval in seconds (default: `30`)

#### 2. Job Progress Events Topic

**Topic Pattern:** `inference/events`

**Purpose:** Real-time job progress updates during execution

**Message Format:**
```json
{
  "event_type": "processing",
  "job_id": "job-abc-123",
  "data": {
    "progress": 50.0
  },
  "timestamp": 1702123456789
}
```

**Event Types:**
- `processing`: Job is being processed (with progress updates)
- `completed`: Job finished successfully
- `error`: Job failed

**Fields:**
- `event_type` (string): Current job status
- `job_id` (string): Unique job identifier
- `data` (object): Event-specific data
  - `progress` (float): Progress percentage (0-100) for `processing` events
- `timestamp` (integer): Unix timestamp in milliseconds

**Behavior:**
- Published when `update_job()` is called with progress updates
- Only published when progress value is provided
- Not retained (real-time events only)
- Respects broadcaster connection status

**Environment Variables:**
- `MQTT_TOPIC`: Override base topic (default: `inference/events`)

### Authentication

**Current Status:** Authentication is **not required** by default.

**To Enable Authentication Later:**

1. **Configure MQTT Broker** with username/password authentication:
   ```bash
   # For Mosquitto broker
   mosquitto_passwd -c /etc/mosquitto/passwd username
   # Edit /etc/mosquitto/mosquitto.conf
   allow_anonymous false
   password_file /etc/mosquitto/passwd
   ```

2. **Update cl_server_shared** to support authentication:
   - Add `MQTT_USERNAME` and `MQTT_PASSWORD` environment variables
   - Modify `MQTTBroadcaster` to accept credentials
   - Call `client.username_pw_set(username, password)` before connecting

3. **Set Environment Variables:**
   ```bash
   export MQTT_USERNAME=worker_user
   export MQTT_PASSWORD=secure_password
   ```

**TLS/SSL Support:**

For encrypted connections, the MQTT broadcaster would need to be updated to support TLS:
- Add `MQTT_USE_TLS` environment variable
- Configure `client.tls_set()` with certificates
- Use port 8883 for TLS connections

## Deployment

The worker can be:
- Run on the same machine as the API service
- Deployed to separate machines (all pointing to the same shared `media_store.db`)
- Scaled horizontally by running multiple instances with different worker IDs
- Configured to handle specific task types per instance
- Run in multi-process environments thanks to WAL mode enabling safe concurrent access

## Migration from compute.db

If upgrading from the old separate `compute.db`:

1. The old `compute.db` is no longer used
2. All new jobs use the merged `media_store.db`
3. You can safely delete the old `compute.db` and its WAL files (`compute.db-wal`, `compute.db-shm`)

```bash
# After confirming all old jobs are completed and archived
rm {CL_SERVER_DIR}/compute.db*
```

## Quick Reference

### All Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CL_SERVER_DIR` | *(required)* | Path to data directory containing `media_store.db` |
| `DATABASE_URL` | `sqlite:///{CL_SERVER_DIR}/media_store.db` | Override database path |
| `WORKER_ID` | `worker-default` | Unique worker identifier |
| `WORKER_SUPPORTED_TASKS` | *(all available)* | Comma-separated task types |
| `WORKER_POLL_INTERVAL` | `5` | Seconds between polls when idle |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC` | `inference/events` | Base topic for job events |
| `MQTT_HEARTBEAT_INTERVAL` | `30` | Heartbeat interval in seconds |
| `CAPABILITY_TOPIC_PREFIX` | `inference/workers` | Base topic for worker capabilities |
| `BROADCAST_TYPE` | `mqtt` | Broadcaster type (`mqtt` or `noop`) |

### MQTT Topic Summary

| Topic | Type | Purpose | Auth Required |
|-------|------|---------|---------------|
| `inference/workers/{worker_id}` | Retained | Worker capability announcements | No (configurable) |
| `inference/events` | Non-retained | Job progress events | No (configurable) |

### Example Subscriber (Python)

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    # Subscribe to all worker capabilities
    client.subscribe("inference/workers/#")
    # Subscribe to job events
    client.subscribe("inference/events")

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    print(f"Topic: {msg.topic}")
    print(f"Message: {json.dumps(payload, indent=2)}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.loop_forever()
```

## MQTT Maintenance

### Cleaning Up Retained Messages

Retained MQTT messages persist until explicitly cleared. Use the provided cleanup script to remove stale messages:

**Clean up test messages:**
```bash
python cleanup_mqtt.py "test/retained/#"
```

**Clean up stale worker capabilities:**
```bash
python cleanup_mqtt.py "inference/workers/#"
```

**Clean up all messages matching a pattern:**
```bash
python cleanup_mqtt.py "your/topic/pattern/#"
```

**Script usage:**
```bash
python cleanup_mqtt.py <topic_pattern> [broker] [port]

# Examples:
python cleanup_mqtt.py "test/#"                    # Clean all test topics
python cleanup_mqtt.py "test/#" mqtt.example.com   # Remote broker
python cleanup_mqtt.py "test/#" localhost 1883     # Explicit broker:port
```

**Manual cleanup (using mosquitto_pub):**
```bash
# Clear a specific retained message
mosquitto_pub -h localhost -t "inference/workers/worker-1" -n -r

# The -n flag sends a null (empty) message
# The -r flag makes it retained (which clears the previous retained message)
```

**Finding retained messages:**
```bash
# Subscribe to all topics and show only retained messages
mosquitto_sub -h localhost -t '#' -v | grep -E "^\w+/\w+"
```
