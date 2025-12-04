"""Shared utilities for compute module - minimal dependencies."""

import os
import json
import logging
import time
from pathlib import Path
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

CL_SERVER_DIR = os.environ.get("CL_SERVER_DIR")
if not CL_SERVER_DIR:
    raise RuntimeError("CL_SERVER_DIR environment variable must be set")

# Use the merged media_store.db instead of separate compute.db
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db")
COMPUTE_DIR = Path(CL_SERVER_DIR) / "compute"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# MQTT configuration
BROADCAST_TYPE = os.environ.get("BROADCAST_TYPE", "mqtt")
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "inference/events")
MQTT_HEARTBEAT_INTERVAL = int(os.environ.get("MQTT_HEARTBEAT_INTERVAL", 30))
CAPABILITY_TOPIC_PREFIX = os.environ.get("CAPABILITY_TOPIC_PREFIX", "inference/workers")

# Worker configuration
WORKER_ID = os.environ.get("WORKER_ID", "worker-default")
WORKER_SUPPORTED_TASKS = os.environ.get(
    "WORKER_SUPPORTED_TASKS", "image_resize,image_conversion"
).split(",")
WORKER_POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", 5))

# ============================================================================
# Database Models
# ============================================================================

class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


class Job(Base):
    """Job model storing metadata, status, and results."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)

    input_file_source: Mapped[str] = mapped_column(String, nullable=False)
    input_file_path: Mapped[str] = mapped_column(String, nullable=False)

    input_files: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    output_files: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    started_at: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    task_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)


# ============================================================================
# Broadcaster
# ============================================================================

class MQTTBroadcaster:
    """MQTT event broadcaster."""

    def __init__(self, broker: str, port: int, topic: str):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client: Optional[mqtt.Client] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            self.client.on_connect = self._on_connect
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            self.connected = True
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

    def publish_event(self, event_type: str, job_id: str, data: dict) -> bool:
        if not self.connected or not self.client:
            return False
        try:
            payload = {
                "job_id": job_id,
                "event_type": event_type,
                "timestamp": int(time.time() * 1000),
                **data,
            }
            result = self.client.publish(self.topic, json.dumps(payload), qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing event: {e}")
            return False

    def set_will(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
        """Set MQTT Last Will and Testament message.

        Called before connect() to configure LWT.

        Args:
            topic: Topic for LWT message
            payload: Payload for LWT message
            qos: QoS level (0, 1, 2)
            retain: Whether to retain the message

        Returns:
            True if successful
        """
        if not self.client:
            return False
        try:
            self.client.will_set(topic, payload, qos=qos, retain=retain)
            return True
        except Exception as e:
            logger.error(f"Error setting LWT: {e}")
            return False

    def publish_retained(self, topic: str, payload: str, qos: int = 1) -> bool:
        """Publish a retained MQTT message.

        Args:
            topic: Topic to publish to
            payload: Message payload (JSON string)
            qos: QoS level (0, 1, 2)

        Returns:
            True if successful
        """
        if not self.connected or not self.client:
            return False
        try:
            result = self.client.publish(topic, payload, qos=qos, retain=True)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing retained message: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)


class NoOpBroadcaster:
    """No-operation broadcaster."""
    def connect(self) -> bool:
        return True
    def disconnect(self):
        pass
    def publish_event(self, event_type: str, job_id: str, data: dict) -> bool:
        return True
    def set_will(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
        return True
    def publish_retained(self, topic: str, payload: str, qos: int = 1) -> bool:
        return True


_broadcaster: Optional[object] = None

def get_broadcaster():
    """Get or create global broadcaster instance."""
    global _broadcaster
    if _broadcaster is not None:
        return _broadcaster
    
    if BROADCAST_TYPE == "mqtt":
        _broadcaster = MQTTBroadcaster(MQTT_BROKER, MQTT_PORT, MQTT_TOPIC)
        _broadcaster.connect()
    else:
        _broadcaster = NoOpBroadcaster()
        _broadcaster.connect()
    
    return _broadcaster

def shutdown_broadcaster():
    """Shutdown broadcaster."""
    global _broadcaster
    if _broadcaster:
        _broadcaster.disconnect()
        _broadcaster = None
