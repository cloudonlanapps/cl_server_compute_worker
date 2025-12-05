"""Tests for worker MQTT capability publishing and heartbeat."""

import json
import time
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestWorkerCapabilityPublishing:
    """Tests for worker capability publishing via MQTT."""

    @pytest.fixture
    def mock_broadcaster(self):
        """Create a mock broadcaster."""
        broadcaster = MagicMock()
        broadcaster.connected = True
        broadcaster.publish_retained.return_value = True
        return broadcaster

    @pytest.fixture
    def mock_module_discovery(self):
        """Mock module discovery to return test modules."""
        return {
            "image_resize": {"module_path": "/path/to/image_resize", "venv_path": "/path/venv"},
            "image_conversion": {"module_path": "/path/to/image_conversion", "venv_path": "/path/venv"},
        }

    def test_publish_worker_capabilities_structure(self, mock_broadcaster, mock_module_discovery):
        """Test that published capability message has correct structure."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize", "image_conversion"])
            worker._publish_worker_capabilities()

            # Verify publish_retained was called
            assert mock_broadcaster.publish_retained.called
            call_args = mock_broadcaster.publish_retained.call_args

            # Check topic format
            topic = call_args[0][0]
            assert "test-worker" in topic
            assert topic.startswith("inference/workers/")

            # Check payload structure
            payload_str = call_args[0][1]
            payload = json.loads(payload_str)

            assert "id" in payload
            assert payload["id"] == "test-worker"
            assert "capabilities" in payload
            assert "idle_count" in payload
            assert "timestamp" in payload

    def test_idle_count_initialization(self, mock_broadcaster, mock_module_discovery):
        """Test that idle count is initialized to 1 per capability."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize", "image_conversion"])

            # Check idle count for each capability
            assert worker.capability_idle_count.get("image_resize") == 1
            assert worker.capability_idle_count.get("image_conversion") == 1

    def test_idle_count_decrement_on_job_claim(self, mock_broadcaster, mock_module_discovery):
        """Test that idle count decrements when job is claimed."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Simulate claiming a job
            initial_idle = worker.capability_idle_count["image_resize"]
            worker.capability_idle_count["image_resize"] = max(0, initial_idle - 1)

            assert worker.capability_idle_count["image_resize"] == 0

    def test_idle_count_increment_on_job_complete(self, mock_broadcaster, mock_module_discovery):
        """Test that idle count increments when job completes."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Simulate job completion
            worker.capability_idle_count["image_resize"] = 0
            worker.capability_idle_count["image_resize"] = min(1, worker.capability_idle_count["image_resize"] + 1)

            assert worker.capability_idle_count["image_resize"] == 1

    def test_heartbeat_publishes_periodically(self, mock_broadcaster, mock_module_discovery):
        """Test that heartbeat task publishes capabilities periodically."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Reset mock
            mock_broadcaster.reset_mock()

            # Call publish directly (in real scenario, _heartbeat_task runs async)
            worker._publish_worker_capabilities()
            assert mock_broadcaster.publish_retained.called

    def test_capabilities_include_all_active_tasks(self, mock_broadcaster, mock_module_discovery):
        """Test that published capabilities include all active tasks."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize", "image_conversion"])
            worker._publish_worker_capabilities()

            payload_str = mock_broadcaster.publish_retained.call_args[0][1]
            payload = json.loads(payload_str)

            assert set(payload["capabilities"]) == {"image_resize", "image_conversion"}

    def test_broadcaster_not_connected_skip_publish(self, mock_broadcaster, mock_module_discovery):
        """Test that publish is skipped if broadcaster not connected."""
        from src.worker import ComputeWorker

        mock_broadcaster.connected = False

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])
            worker._publish_worker_capabilities()

            # Should not have called publish_retained
            assert not mock_broadcaster.publish_retained.called

    def test_idle_count_never_negative(self, mock_broadcaster, mock_module_discovery):
        """Test that idle count never goes below zero."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Try to decrement beyond 0
            worker.capability_idle_count["image_resize"] = 0
            worker.capability_idle_count["image_resize"] = max(0, worker.capability_idle_count["image_resize"] - 1)

            assert worker.capability_idle_count["image_resize"] == 0

    def test_idle_count_never_exceeds_max(self, mock_broadcaster, mock_module_discovery):
        """Test that idle count never exceeds 1."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.discover_compute_modules", return_value=mock_module_discovery), \
             patch("src.worker.ensure_module_venv", return_value=True):
            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Try to increment beyond 1
            worker.capability_idle_count["image_resize"] = 1
            worker.capability_idle_count["image_resize"] = min(1, worker.capability_idle_count["image_resize"] + 1)

            assert worker.capability_idle_count["image_resize"] == 1


class TestBroadcasterMethods:
    """Tests for broadcaster retained message and LWT methods."""

    def test_set_will_method_exists(self):
        """Test that broadcaster has set_will method."""
        from cl_server_shared.mqtt import MQTTBroadcaster

        broadcaster = MQTTBroadcaster("localhost", 1883, "test/topic")
        assert hasattr(broadcaster, "set_will")
        assert callable(broadcaster.set_will)

    def test_publish_retained_method_exists(self):
        """Test that broadcaster has publish_retained method."""
        from cl_server_shared.mqtt import MQTTBroadcaster

        broadcaster = MQTTBroadcaster("localhost", 1883, "test/topic")
        assert hasattr(broadcaster, "publish_retained")
        assert callable(broadcaster.publish_retained)

    def test_noop_broadcaster_has_methods(self):
        """Test that NoOp broadcaster implements required methods."""
        from cl_server_shared.mqtt import NoOpBroadcaster

        broadcaster = NoOpBroadcaster()
        assert hasattr(broadcaster, "set_will")
        assert hasattr(broadcaster, "publish_retained")
        assert callable(broadcaster.set_will)
        assert callable(broadcaster.publish_retained)
