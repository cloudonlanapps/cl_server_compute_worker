"""
Subprocess runner for image_conversion.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Import from local shared module
from .shared import DATABASE_URL, COMPUTE_DIR, LOG_LEVEL, Job, Base, get_broadcaster, shutdown_broadcaster

# Import local task
from .task import ImageConversionModule

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("image_conversion-runner")


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


def main():
    parser = argparse.ArgumentParser(description="Run a compute job")
    parser.add_argument("--job-id", required=True, help="Job ID to process")
    args = parser.parse_args()

    job_id = args.job_id
    logger.info(f"Runner started for job {job_id}")

    # Setup database
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Needed for SQLite with multiple processes
        echo=False
    )

    # Register WAL event listener for every connection
    if "sqlite" in DATABASE_URL.lower():
        event.listen(engine, "connect", _enable_wal_mode)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Setup broadcaster
    broadcaster = get_broadcaster()

    try:
        # 1. Get Job
        job = db.query(Job).filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            sys.exit(1)

        # 2. Update Status -> Processing
        job.status = "processing"
        job.started_at = int(time.time() * 1000)
        db.commit()
        
        broadcaster.publish_event("started", job_id, {"status": "processing"})

        # 3. Prepare Inputs
        task_type = job.task_type
        input_files_info = json.loads(job.input_files)
        input_files = []
        for file_info in input_files_info:
            file_path = Path(COMPUTE_DIR) / file_info.get("path")
            if file_path.exists() or file_path.is_symlink():
                input_files.append(file_path)
            else:
                logger.warning(f"Input file not found: {file_path}")

        if not input_files:
            raise ValueError("No input files found")

        metadata = input_files_info[0].get("metadata", {}) if input_files_info else {}

        # 4. Load Module
        logger.info(f"Loading module for {task_type}")
        # Direct instantiation of the local module
        module = ImageConversionModule()

        # 5. Define Progress Callback
        def progress_callback(percentage: int):
            try:
                job.progress = min(99, percentage)
                db.commit()
                broadcaster.publish_event("progress", job_id, {"progress": percentage})
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")

        # 6. Execute (Async wrapper)
        logger.info("Executing module...")
        result = _execute_async_module(module, job_id, input_files, metadata, progress_callback)

        # 7. Handle Result
        status = result.get("status", "error")
        error = result.get("error")
        output_files = result.get("output_files", [])
        task_output = result.get("task_output", {})

        if status == "ok":
            logger.info("Job completed successfully")
            job.status = "completed"
            job.progress = 100
            job.output_files = json.dumps(output_files)
            job.task_output = json.dumps(task_output)
            job.completed_at = int(time.time() * 1000)
            db.commit()
            broadcaster.publish_event("completed", job_id, {"output_files": output_files})
        else:
            logger.error(f"Job failed: {error}")
            job.status = "error"
            job.error_message = error
            job.completed_at = int(time.time() * 1000)
            db.commit()
            broadcaster.publish_event("failed", job_id, {"error": error})
            sys.exit(1)

    except Exception as e:
        logger.exception(f"Runner exception: {e}")
        try:
            job = db.query(Job).filter_by(job_id=job_id).first()
            if job:
                job.status = "error"
                job.error_message = str(e)
                job.completed_at = int(time.time() * 1000)
                db.commit()
                broadcaster.publish_event("failed", job_id, {"error": str(e)})
        except:
            pass
        sys.exit(1)
    finally:
        db.close()
        shutdown_broadcaster()

def _execute_async_module(module, job_id, input_files, metadata, progress_callback):
    """Execute async compute module in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            module.process(job_id, input_files, metadata, progress_callback)
        )
        return result
    finally:
        loop.close()

if __name__ == "__main__":
    main()
