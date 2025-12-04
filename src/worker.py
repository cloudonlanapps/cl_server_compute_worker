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

# Import from local shared module
from .shared import DATABASE_URL, WORKER_ID, WORKER_SUPPORTED_TASKS, WORKER_POLL_INTERVAL, LOG_LEVEL, Base, Job

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
                "module_name": "image_resize",
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
    
    registry = {}
    
    for module_dir in modules_dir.iterdir():
        if not module_dir.is_dir() or module_dir.name.startswith('.'):
            continue
        
        # Check for required files
        runner_path = module_dir / "runner.py"
        task_path = module_dir / "task.py"
        pyproject_path = module_dir / "pyproject.toml"
        
        if not all([runner_path.exists(), task_path.exists(), pyproject_path.exists()]):
            logger.warning(f"Skipping incomplete module: {module_dir.name}")
            continue
        
        # Use folder name as task type (e.g., "image_resize", "image_conversion")
        task_type = module_dir.name
        
        venv_path = module_dir / ".venv"
        python_path = venv_path / "bin" / "python"
        
        registry[task_type] = {
            "module_name": module_dir.name,
            "module_path": module_dir,
            "runner_path": runner_path,
            "venv_path": venv_path,
            "python_path": python_path
        }
        
        logger.info(f"Discovered module: {module_dir.name} -> {task_type}")
    
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
    
    if python_path.exists():
        logger.info(f"Virtual environment exists for {module_info['module_name']}")
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
        
        # Discover and setup compute modules
        self.module_registry = discover_compute_modules()
        
        # Filter to only supported tasks
        available_tasks = set(self.module_registry.keys())
        requested_tasks = set(self.supported_tasks)
        self.active_tasks = available_tasks & requested_tasks
        
        if not self.active_tasks:
            logger.warning(f"No matching modules found for tasks: {self.supported_tasks}")
        
        logger.info(f"Initialized worker {self.worker_id}")
        logger.info(f"Active task types: {list(self.active_tasks)}")
        
        # Ensure venvs exist for active modules
        for task_type in self.active_tasks:
            module_info = self.module_registry[task_type]
            if not ensure_module_venv(module_info):
                logger.error(f"Failed to setup venv for {task_type}, removing from active tasks")
                self.active_tasks.remove(task_type)

    async def run(self):
        """Main worker loop."""
        logger.info(f"Worker {self.worker_id} starting...")

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

    async def _process_next_job(self) -> bool:
        """Poll DB and process one job if available."""
        db = SessionLocal()
        try:
            # Find a PENDING job that matches our active tasks
            jobs = (
                db.query(Job)
                .filter(Job.status == "pending")
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
                current_job = db.query(Job).filter_by(job_id=job.job_id, status="pending").first()
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

    # Create and run worker
    worker = ComputeWorker(
        worker_id=args.worker_id,
        supported_tasks=tasks
    )

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
