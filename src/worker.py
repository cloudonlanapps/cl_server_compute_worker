import asyncio
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict
import json

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Import from cl_server_shared
try:
    from cl_server_shared import (
        WORKER_DATABASE_URL as DATABASE_URL,
        WORKER_ID,
        WORKER_SUPPORTED_TASKS,
        WORKER_POLL_INTERVAL,
        LOG_LEVEL,
        Job,
        MQTT_HEARTBEAT_INTERVAL,
        CAPABILITY_TOPIC_PREFIX,
        BROADCAST_TYPE,
        MQTT_BROKER,
        MQTT_PORT,
        MQTT_TOPIC,
    )
    from cl_server_shared.database import Base
    from cl_server_shared.mqtt import get_broadcaster, shutdown_broadcaster
except ImportError:
    # Fallback if package not installed (e.g. during development)
    logger.warning("cl_server_shared not found, using local fallbacks (this should not happen in production)")
    raise

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger.setLevel(LOG_LEVEL)


def _enable_wal_mode(dbapi_conn, connection_record):
    """Enable WAL mode and set optimization pragmas for SQLite."""
    cursor = dbapi_conn.cursor()
    # WAL mode enables concurrent reads and single writer
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Setup database
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite with multiple processes
    echo=False
)

# Register WAL event listener for every connection
if "sqlite" in DATABASE_URL.lower():
    event.listen(engine, "connect", _enable_wal_mode)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# Shutdown event
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


def discover_compute_modules() -> Dict[str, Dict]:
    """
    Discover compute modules in compute_modules/ directory.

    Returns:
        Dict mapping task_type to module info:
        {
            "image_resize": {
                "module_name": "image_processor",
                "module_path": Path(...),
                "runner_path": Path(...),
                "venv_path": Path(...),
                "python_path": Path(...)
            }
        }
    """
    modules_dir = Path(__file__).parent.parent / "compute_modules"
    if not modules_dir.exists():
        logger.warning(f"Compute modules directory not found: {modules_dir}")
        return {}

    logger.info(f"Scanning for compute modules in: {modules_dir}")
    registry = {}

    import tomllib  # For parsing pyproject.toml (Python 3.11+)

    for module_dir in modules_dir.iterdir():
        if not module_dir.is_dir() or module_dir.name.startswith('.'):
            continue

        # Check for required files in src/ subdirectory
        src_dir = module_dir / "src"
        runner_path = src_dir / "runner.py"
        pyproject_path = module_dir / "pyproject.toml"

        # Log what we're checking
        logger.debug(f"Checking module: {module_dir.name}")
        logger.debug(f"  - runner.py exists at {runner_path}: {runner_path.exists()}")
        logger.debug(f"  - pyproject.toml exists at {pyproject_path}: {pyproject_path.exists()}")

        if not all([runner_path.exists(), pyproject_path.exists()]):
            logger.warning(f"Skipping incomplete module: {module_dir.name} (missing required files in src/)")
            continue

        # Parse pyproject.toml for supported tasks
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)
            
            supported_tasks = pyproject_data.get("tool", {}).get("compute_module", {}).get("supported_tasks", [])
            
            if not supported_tasks:
                logger.warning(f"Skipping module {module_dir.name}: No supported_tasks defined in [tool.compute_module]")
                continue
                
        except Exception as e:
            logger.error(f"Failed to parse pyproject.toml for {module_dir.name}: {e}")
            continue

        venv_path = module_dir / ".venv"
        python_path = venv_path / "bin" / "python"

        module_info = {
            "module_name": module_dir.name,
            "module_path": module_dir,
            "runner_path": runner_path,
            "venv_path": venv_path,
            "python_path": python_path
        }

        # Register module for each supported task
        for task_type in supported_tasks:
            if task_type in registry:
                # Conflict detected!
                existing_module = registry[task_type]["module_name"]
                error_msg = f"Conflict detected! Task '{task_type}' is already registered by module '{existing_module}'."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            registry[task_type] = module_info
            logger.info(f"✓ Discovered module: {module_dir.name} -> {task_type}")

    logger.info(f"Total tasks discovered: {len(registry)}")
    logger.info(f"Available task types: {list(registry.keys())}")

    return registry


def ensure_module_venv(module_info: Dict) -> bool:
    """
    Ensure virtual environment exists for a module.
    
    Returns:
        True if venv is ready, False otherwise
    """
    module_path = module_info["module_path"]
    venv_path = module_info["venv_path"]
    python_path = module_info["python_path"]
    
    # Path to cl_server_shared (relative to module directory)
    # module_dir is cl_server_compute_worker/compute_modules/<module>
    # cl_server_shared is cl_server_shared/
    # So we need to go up 3 levels: ../../../cl_server_shared
    shared_pkg_path = Path(__file__).parent.parent.parent / "cl_server_shared"
    
    if python_path.exists():
        logger.info(f"Virtual environment exists for {module_info['module_name']}")
        # Ensure cl_server_shared is installed even if venv exists
        try:
             subprocess.run(
                [str(python_path), "-m", "pip", "install", "-q", "-e", str(shared_pkg_path)],
                check=True,
                cwd=str(module_path)
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to update cl_server_shared for {module_info['module_name']}: {e}")
        return True
    
    logger.info(f"Creating virtual environment for {module_info['module_name']}...")
    
    try:
        # Create venv
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            cwd=str(module_path)
        )
        
        # Install module in editable mode with its dependencies from pyproject.toml
        subprocess.run(
            [str(python_path), "-m", "pip", "install", "-q", "-e", "."],
            check=True,
            cwd=str(module_path)
        )

        # Install cl_server_shared in editable mode
        if shared_pkg_path.exists():
             subprocess.run(
                [str(python_path), "-m", "pip", "install", "-q", "-e", str(shared_pkg_path)],
                check=True,
                cwd=str(module_path)
            )
        else:
            logger.error(f"cl_server_shared not found at {shared_pkg_path}")
            return False
        
        logger.info(f"Virtual environment created for {module_info['module_name']}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create venv for {module_info['module_name']}: {e}")
        return False


class ComputeWorker:
    """Main compute worker that polls SQLite and spawns subprocesses."""

    def __init__(
        self,
        worker_id: str = WORKER_ID,
        supported_tasks: Optional[List[str]] = None,
        poll_interval: int = WORKER_POLL_INTERVAL,
    ):
        """Initialize compute worker."""
        self.worker_id = worker_id
        self.supported_tasks = supported_tasks or WORKER_SUPPORTED_TASKS
        self.poll_interval = poll_interval
        self.broadcaster = get_broadcaster(
            broadcast_type=BROADCAST_TYPE,
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            topic=MQTT_TOPIC
        )

        # Track idle count for each capability (task type)
        self.capability_idle_count = {}

        # Discover and setup compute modules
        self.module_registry = discover_compute_modules()

        # Filter to only supported tasks
        available_tasks = set(self.module_registry.keys())
        requested_tasks = set(self.supported_tasks)
        self.active_tasks = available_tasks & requested_tasks

        # Log initialization details
        logger.info(f"Initialized worker {self.worker_id}")
        logger.info(f"Requested task types: {list(requested_tasks)}")
        logger.info(f"Available modules: {list(available_tasks)}")
        logger.info(f"Active task types: {list(self.active_tasks)}")

        if not self.active_tasks:
            if requested_tasks and not available_tasks:
                logger.error(f"No modules found! Requested: {list(requested_tasks)}, Available: {list(available_tasks)}")
            elif requested_tasks and available_tasks:
                logger.warning(f"No matching modules found. Requested: {list(requested_tasks)}, Available: {list(available_tasks)}")
            else:
                logger.warning(f"No task types specified")

        # Initialize idle count to 1 for each task (can process 1 job at a time)
        for task_type in self.active_tasks:
            self.capability_idle_count[task_type] = 1

        # Ensure venvs exist for active modules
        for task_type in self.active_tasks:
            module_info = self.module_registry[task_type]
            if not ensure_module_venv(module_info):
                logger.error(f"Failed to setup venv for {task_type}, removing from active tasks")
                self.active_tasks.remove(task_type)

    def _publish_worker_capabilities(self):
        """Publish worker capabilities to MQTT with retained message."""
        if not self.broadcaster.connected:
            logger.warning("MQTT broadcaster not connected, skipping capability publish")
            return

        capabilities_msg = {
            "id": self.worker_id,
            "capabilities": list(self.active_tasks),
            "idle_count": sum(self.capability_idle_count.values()),
            "timestamp": int(time.time() * 1000),
            # Debug info: include all available modules and requested tasks
            "_debug": {
                "requested_tasks": list(self.supported_tasks),
                "discovered_modules": list(self.module_registry.keys()),
                "active_tasks": list(self.active_tasks),
                "module_registry_keys": list(self.module_registry.keys()),
            }
        }

        topic = f"{CAPABILITY_TOPIC_PREFIX}/{self.worker_id}"
        payload = json.dumps(capabilities_msg)

        success = self.broadcaster.publish_retained(topic, payload, qos=1)
        if success:
            logger.info(f"Published worker capabilities to {topic}")
            logger.info(f"  - Requested tasks: {list(self.supported_tasks)}")
            logger.info(f"  - Available modules: {list(self.module_registry.keys())}")
            logger.info(f"  - Active capabilities: {list(self.active_tasks)}")
            logger.info(f"  - Idle count: {sum(self.capability_idle_count.values())}")
        else:
            logger.error(f"Failed to publish worker capabilities to {topic}")

    async def _heartbeat_task(self):
        """Background task to publish heartbeat periodically."""
        logger.info(f"Heartbeat task started for {self.worker_id} (interval: {MQTT_HEARTBEAT_INTERVAL}s)")
        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(MQTT_HEARTBEAT_INTERVAL)
                if not shutdown_event.is_set():
                    self._publish_worker_capabilities()
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat task: {e}")

    async def run(self):
        """Main worker loop."""
        logger.info(f"Worker {self.worker_id} starting...")

        # Publish initial capabilities
        self._publish_worker_capabilities()

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_task())

        try:
            while not shutdown_event.is_set():
                try:
                    processed = await self._process_next_job()
                    if not processed:
                        # No job found, sleep
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    logger.info("Worker cancelled")
                    break
                except Exception as e:
                    logger.exception(f"Error in worker loop: {e}")
                    await asyncio.sleep(self.poll_interval)
        finally:
            logger.info(f"Worker {self.worker_id} shutting down...")
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _process_next_job(self) -> bool:
        """Poll DB and process one job if available."""
        db = SessionLocal()
        try:
            # Find a QUEUED job that matches our active tasks
            jobs = (
                db.query(Job)
                .filter(Job.status == "queued")
                .filter(Job.task_type.in_(list(self.active_tasks)))
                .order_by(Job.created_at.asc())
                .limit(5)
                .all()
            )

            if not jobs:
                return False

            # Try to claim one
            claimed_job = None
            for job in jobs:
                current_job = db.query(Job).filter_by(job_id=job.job_id, status="queued").first()
                if current_job:
                    current_job.status = "claimed"
                    try:
                        db.commit()
                        claimed_job = current_job
                        break
                    except Exception:
                        db.rollback()
                        continue
            
            if not claimed_job:
                return False

            # Get module info for this task type
            module_info = self.module_registry.get(claimed_job.task_type)
            if not module_info:
                logger.error(f"No module found for task type: {claimed_job.task_type}")
                return False

            logger.info(f"Claimed job {claimed_job.job_id} ({claimed_job.task_type})")

            # Decrement idle count for this task type
            task_type = claimed_job.task_type
            if task_type in self.capability_idle_count:
                self.capability_idle_count[task_type] = max(0, self.capability_idle_count[task_type] - 1)
                logger.debug(f"Decremented idle count for {task_type}: {self.capability_idle_count[task_type]}")
                # Publish updated capabilities
                self._publish_worker_capabilities()

            db.close()

            # Spawn subprocess using module-specific python and runner
            cmd = [
                str(module_info["python_path"]),
                str(module_info["runner_path"]),
                "--job-id",
                claimed_job.job_id
            ]

            logger.info(f"Spawning subprocess: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(module_info["module_path"])
            )

            stdout, stderr = await process.communicate()

            # Increment idle count when job completes
            if task_type in self.capability_idle_count:
                self.capability_idle_count[task_type] = min(1, self.capability_idle_count[task_type] + 1)
                logger.debug(f"Incremented idle count for {task_type}: {self.capability_idle_count[task_type]}")
                # Publish updated capabilities
                self._publish_worker_capabilities()

            if process.returncode == 0:
                logger.info(f"Job {claimed_job.job_id} subprocess finished successfully")
            else:
                logger.error(f"Job {claimed_job.job_id} subprocess failed with code {process.returncode}")
                logger.error(f"Stderr: {stderr.decode()}")
                self._ensure_job_failed(claimed_job.job_id, f"Subprocess crashed with code {process.returncode}")

            return True

        except Exception as e:
            logger.exception(f"Error processing queue: {e}")
            return False
        finally:
            db.close()

    def _ensure_job_failed(self, job_id, error_msg):
        """Ensure job is marked as failed if subprocess crashed."""
        db = SessionLocal()
        try:
            job = db.query(Job).filter_by(job_id=job_id).first()
            if job and job.status not in ["completed", "error"]:
                logger.warning(f"Marking crashed job {job_id} as error")
                job.status = "error"
                job.error_message = error_msg
                job.completed_at = int(time.time() * 1000)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update crashed job status: {e}")
        finally:
            db.close()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", default=WORKER_ID)
    parser.add_argument("--tasks", default=None, help="Comma-separated list of tasks")
    args = parser.parse_args()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tasks = args.tasks.split(",") if args.tasks else None
    worker_id = args.worker_id

    # Setup MQTT LWT (Last Will & Testament) before connecting
    broadcaster = get_broadcaster(
        broadcast_type=BROADCAST_TYPE,
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        topic=MQTT_TOPIC
    )
    lwt_topic = f"{CAPABILITY_TOPIC_PREFIX}/{worker_id}"
    broadcaster.set_will(lwt_topic, "", qos=1, retain=True)

    # Create and run worker
    worker = ComputeWorker(
        worker_id=worker_id,
        supported_tasks=tasks
    )

    try:
        await worker.run()
    finally:
        # Shutdown broadcaster
        shutdown_broadcaster()


if __name__ == "__main__":
    asyncio.run(main())
