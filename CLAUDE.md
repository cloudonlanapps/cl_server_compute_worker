# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a standalone compute worker service that processes media processing jobs from a shared SQLite database (`media_store.db`) using Write-Ahead Logging (WAL) mode for safe concurrent access. The worker leverages two external libraries:
- **cl_server_shared**: Provides database models, MQTT broadcast capabilities, configuration, and repository adapters
- **cl_media_tools**: Provides the job processing engine and task plugins via entry points

The worker is independent from any API service and communicates via database and MQTT.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (editable mode for development)
pip install -e .

# Install test dependencies
pip install -e ".[test]"
```

### Running Tests
```bash
# Run all tests
./run_all_tests.sh

# Run specific test file
python -m pytest tests/test_worker.py -v

# Run tests with coverage
python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

### Starting the Worker
```bash
# Using the start script (requires environment variables)
export CL_VENV_DIR=/path/to/venv/parent
export CL_SERVER_DIR=/path/to/data
./start_worker.sh --worker-id worker-1 --tasks image_resize,image_conversion

# Direct Python execution
python main.py --worker-id worker-1 --tasks image_resize
```

## Architecture

### Component Relationships

```
ComputeWorker (src/worker.py)
    ├── Uses cl_media_tools.worker.Worker (job processing engine)
    │   └── Discovers task handlers via entry points
    ├── Uses cl_server_shared.adapters.SQLAlchemyJobRepository (database access)
    │   └── Wraps SQLAlchemy sessions to conform to cl_media_tools interface
    └── Uses cl_server_shared.mqtt.get_broadcaster() (MQTT publishing)
        └── Publishes worker capabilities and heartbeats
```

### Job Processing Flow

1. **Initialization**: Worker creates `cl_media_tools.Worker` instance with repository adapter
2. **Task Discovery**: Library discovers available task handlers from installed plugins via entry points
3. **Task Filtering**: Worker filters to only `active_tasks` (intersection of requested and available)
4. **Job Polling**: Calls `library_worker.run_once(task_types)` which:
   - Atomically claims a pending job from database
   - Executes the job using the appropriate plugin
   - Updates job status in database
5. **Capability Broadcasting**: Worker publishes idle/busy status to MQTT

### Database Access (WAL Mode)

All database connections automatically enable Write-Ahead Logging (WAL) mode via SQLAlchemy event listeners in `cl_server_shared`. This allows:
- Multiple worker processes to read concurrently
- Safe concurrent writes (SQLite handles locking)
- No database lock contention

The database creates three files automatically:
- `media_store.db` - Main database
- `media_store.db-wal` - Write-Ahead Log
- `media_store.db-shm` - Shared memory

### MQTT Capabilities

The worker publishes retained capability messages to MQTT topic `{CAPABILITY_TOPIC_PREFIX}/{worker_id}`:
```json
{
  "id": "worker-1",
  "capabilities": ["image_resize", "image_conversion"],
  "idle_count": 1,  // 0 when busy, 1 when idle
  "timestamp": 1234567890
}
```

#### Retained Message Lifecycle

Retained messages are persistent in MQTT and do not have timeouts. The worker manages their lifecycle explicitly:

1. **On Startup**: Worker publishes retained capability message to announce availability
2. **During Operation**: Heartbeat task periodically refreshes the message with updated idle/busy status
3. **On Shutdown**: Worker explicitly clears the retained message to prevent stale worker registrations

**Shutdown Sequence**:
1. Cancel heartbeat task to stop publishing new capabilities
2. Wait for heartbeat task to complete
3. Call `clear_retained()` to remove the retained capability message
4. Shutdown MQTT broadcaster connection

**Abnormal Disconnect**: Last Will & Testament (LWT) is configured to send an empty retained message when the broker detects an unexpected disconnect, ensuring the capability is cleared even if the worker crashes.

## Configuration

Configuration is loaded from environment variables via `cl_server_shared`:

### Required Environment Variables
- `CL_SERVER_DIR` - Path to data directory (contains `media_store.db`)
- `CL_VENV_DIR` - Path to parent directory for virtual environments (used by start script)

### Optional Environment Variables
- `DATABASE_URL` - Override default database path (default: `sqlite:///{CL_SERVER_DIR}/media_store.db`)
- `WORKER_ID` - Worker identifier (default: `worker-default`)
- `WORKER_SUPPORTED_TASKS` - Comma-separated task types (default: all available)
- `WORKER_POLL_INTERVAL` - Seconds between polls when idle (default: 5)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `MQTT_BROKER` - MQTT broker host (default: `localhost`)
- `MQTT_PORT` - MQTT broker port (default: 1883)
- `MQTT_TOPIC` - Base MQTT topic (default: `cl_server`)
- `MQTT_HEARTBEAT_INTERVAL` - Seconds between heartbeats (default: 30)
- `BROADCAST_TYPE` - Broadcaster type: `mqtt` or `noop` (default: `mqtt`)

## External Dependencies

### cl_server_shared
Git package: `git+https://github.com/cloudonlanapps/cl_server_shared.git`

Provides:
- Database models (`ComputeJob`, `ComputeJobStatus` enums)
- Configuration loading from environment variables
- `SQLAlchemyJobRepository` adapter (wraps SQLAlchemy for cl_media_tools)
- MQTT broadcaster factory and singleton management
- Database engine and session factory with WAL mode

### cl_media_tools[compute]
Git package: `git+https://github.com/cloudonlanapps/cl_media_tools.git`

Provides:
- `Worker` class for job processing
- Entry point discovery for task plugins
- Job execution framework
- Repository interface (implemented by cl_server_shared adapter)

Task plugins are discovered via entry points. Built-in plugins: `image_resize`, `image_conversion`.

## Testing Strategy

Tests use mocks for external dependencies:
- Mock `cl_media_tools.Worker` to test integration
- Mock `SQLAlchemyJobRepository` to avoid database
- Mock `get_broadcaster()` to avoid MQTT connection

Key test coverage:
- Worker initialization with task filtering
- Job processing success/failure
- MQTT capability publishing
- Heartbeat task lifecycle

## Important Patterns

### Asyncio Event Loop
The worker uses `asyncio` for:
- Main polling loop (`worker.run()`)
- Background heartbeat task
- Graceful shutdown via `shutdown_event`

Signal handlers (SIGINT, SIGTERM) set the shutdown event to stop the worker cleanly.

### Repository Adapter Pattern
`SQLAlchemyJobRepository` in `cl_server_shared` implements the interface expected by `cl_media_tools.Worker`, translating between SQLAlchemy models and the library's domain models.

### Broadcaster Singleton
`get_broadcaster()` returns a singleton instance per process. Call `shutdown_broadcaster()` on exit to clean up connections.

## Migration Notes

This worker previously used a subprocess-based architecture with separate `compute_modules/`. That has been replaced with the `cl_media_tools` library approach where plugins are installed packages discovered via entry points. Old references to `compute_modules/` in `run_all_tests.sh` are legacy.

The database was previously `compute.db` but has been merged into `media_store.db`.
