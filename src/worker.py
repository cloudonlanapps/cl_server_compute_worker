"""Compute worker using cl_ml_tools library.

This worker uses the cl_ml_tools library for in-process job execution,
replacing the previous subprocess-based approach. Jobs are discovered via
entry points and executed directly using the library's Worker class.
"""

import asyncio
import json
import logging
import signal
import time
from typing import Optional, List, Union

from cl_ml_tools import Worker, MQTTBroadcaster, NoOpBroadcaster


# Import from cl_server_shared
from cl_server_shared import (
    WORKER_DATABASE_URL as DATABASE_URL,
    WORKER_ID,
    WORKER_SUPPORTED_TASKS,
    WORKER_POLL_INTERVAL,
    LOG_LEVEL,
    MQTT_HEARTBEAT_INTERVAL,
    CAPABILITY_TOPIC_PREFIX,
    BROADCAST_TYPE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    get_broadcaster,
    shutdown_broadcaster,
)
from cl_server_shared.database import create_db_engine, create_session_factory
from cl_server_shared.adapters import SQLAlchemyJobRepository

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger.setLevel(LOG_LEVEL)

# Setup database
engine = create_db_engine(DATABASE_URL, echo=False)
SessionLocal = create_session_factory(engine)

# Shutdown event
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


class ComputeWorker:
    """Compute worker using cl_ml_tools library for in-process execution."""

    def __init__(
        self,
        worker_id: str = WORKER_ID,
        supported_tasks: Optional[List[str]] = None,
        poll_interval: int = WORKER_POLL_INTERVAL,
        broadcaster: Optional[Union[MQTTBroadcaster, NoOpBroadcaster]] = None,
    ):
        """Initialize compute worker.

        Args:
            worker_id: Unique identifier for this worker
            supported_tasks: List of task types to process (None = all available)
            poll_interval: Seconds between polls when no jobs available
        """
        self.worker_id = worker_id
        self.requested_tasks = supported_tasks or WORKER_SUPPORTED_TASKS
        self.poll_interval = poll_interval

        # Create repository adapter
        self.repository = SQLAlchemyJobRepository(SessionLocal)

        # Create cl_ml_tools Worker
        self.library_worker = Worker(repository=self.repository)

        # Get available task types from library
        available_tasks = set(self.library_worker.get_supported_task_types())
        requested_tasks = (
            set(self.requested_tasks) if self.requested_tasks else available_tasks
        )

        # Active tasks are the intersection of requested and available
        self.active_tasks = available_tasks & requested_tasks

        # Log initialization details
        logger.info(f"Initialized worker {self.worker_id}")
        logger.info(f"Requested task types: {list(requested_tasks)}")
        logger.info(f"Available task types from plugins: {list(available_tasks)}")
        logger.info(f"Active task types: {list(self.active_tasks)}")

        if not self.active_tasks:
            if requested_tasks and not available_tasks:
                logger.error(
                    "No plugins found! Check that cl_ml_tools is installed with plugins."
                )
            elif requested_tasks and available_tasks:
                logger.warning(
                    f"No matching plugins found. Requested: {list(requested_tasks)}, "
                    f"Available: {list(available_tasks)}"
                )
            else:
                logger.warning("No task types specified")
            raise Exception("No tasks assigned")

        # Initialize MQTT broadcaster. Avoid creating a default broadcaster
        # at function-definition time (it may come from a different package
        # on sys.path). Prefer `get_broadcaster` when available, else
        # instantiate a NoOpBroadcaster safely.
        if broadcaster is not None:
            self.broadcaster = broadcaster

        else:
            try:
                # Prefer the shared get_broadcaster factory
                self.broadcaster = get_broadcaster(
                    BROADCAST_TYPE, MQTT_BROKER, MQTT_PORT
                )
            except Exception:
                raise

        # Track idle count for capability publishing
        # For now, we process one job at a time, so idle count is 0 or 1
        self.is_idle = True

    def _publish_worker_capabilities(self):
        """Publish worker capabilities to MQTT with retained message."""
        if not self.broadcaster:
            logger.warning("MQTT broadcaster not setup, skipping capability publish")
            return
        if not self.broadcaster.connected:
            logger.warning(
                "MQTT broadcaster not connected, skipping capability publish"
            )
            return

        capabilities_msg = {
            "id": self.worker_id,
            "capabilities": list(self.active_tasks),
            "idle_count": 1 if self.is_idle else 0,
            "timestamp": int(time.time() * 1000),
        }

        topic = f"{CAPABILITY_TOPIC_PREFIX}/{self.worker_id}"
        payload = json.dumps(capabilities_msg)

        success = self.broadcaster.publish_retained(topic=topic, payload=payload, qos=1)
        if success:
            logger.info(f"Published worker capabilities to {topic}")
            logger.info(f"  - Active capabilities: {list(self.active_tasks)}")
            logger.info(f"  - Idle: {self.is_idle}")
        else:
            logger.error(f"Failed to publish worker capabilities to {topic}")

    def _clear_worker_capabilities(self):
        """Clear retained worker capabilities from MQTT."""
        if not self.broadcaster:
            logger.warning("MQTT broadcaster not setup, skipping capability publish")
            return
        if not self.broadcaster.connected:
            logger.warning("MQTT broadcaster not connected, skipping capability clear")
            return

        topic = f"{CAPABILITY_TOPIC_PREFIX}/{self.worker_id}"

        success = self.broadcaster.clear_retained(topic)
        if success:
            logger.info(f"Cleared retained worker capabilities from {topic}")
        else:
            logger.error(f"Failed to clear retained worker capabilities from {topic}")

    async def _heartbeat_task(self):
        """Background task to publish heartbeat periodically."""
        logger.info(
            f"Heartbeat task started for {self.worker_id} "
            f"(interval: {MQTT_HEARTBEAT_INTERVAL}s)"
        )
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

            # Cancel heartbeat task first to prevent race conditions
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Clear retained capability message after heartbeat is stopped
            self._clear_worker_capabilities()

    async def _process_next_job(self) -> bool:
        """Process one job using cl_ml_tools Worker.

        Returns:
            True if a job was processed, False if no jobs available
        """
        # Mark as busy
        self.is_idle = False
        self._publish_worker_capabilities()

        try:
            # Use library worker to fetch and process job
            # Pass active tasks as filter
            task_types = list(self.active_tasks) if self.active_tasks else None
            processed = await self.library_worker.run_once(task_types=task_types)

            if processed:
                logger.info("Job processed successfully")
                return True
            else:
                logger.debug("No jobs available")
                return False

        except Exception as e:
            logger.exception(f"Error processing job: {e}")
            return False
        finally:
            # Mark as idle
            self.is_idle = True
            self._publish_worker_capabilities()


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
    )
    lwt_topic = f"{CAPABILITY_TOPIC_PREFIX}/{worker_id}"

    broadcaster.set_will(topic=lwt_topic, payload="", qos=1, retain=True)

    # Create and run worker
    worker = ComputeWorker(
        worker_id=worker_id, supported_tasks=tasks, broadcaster=broadcaster
    )

    try:
        await worker.run()
    finally:
        # Shutdown broadcaster
        shutdown_broadcaster()


if __name__ == "__main__":
    asyncio.run(main())
