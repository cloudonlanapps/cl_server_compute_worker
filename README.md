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
