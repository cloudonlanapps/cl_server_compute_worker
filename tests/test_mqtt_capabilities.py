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

    def test_publish_worker_capabilities_structure(self, mock_broadcaster):
        """Test that published capability message has correct structure."""
        from src.worker import ComputeWorker

        # Mock the library Worker
        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize", "image_conversion"]
            mock_worker_class.return_value = mock_library_worker

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

    def test_idle_state_initialization(self, mock_broadcaster):
        """Test that worker starts in idle state."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize", "image_conversion"]
            mock_worker_class.return_value = mock_library_worker

            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize", "image_conversion"])

            # Worker should start idle
            assert worker.is_idle is True

    def test_idle_state_during_job_processing(self, mock_broadcaster):
        """Test that is_idle flag changes during job processing."""
        from src.worker import ComputeWorker
        import asyncio

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize"]

            # Track state changes
            idle_states = []
            async def mock_run_once(task_types):
                idle_states.append(worker.is_idle)
                return True

            mock_library_worker.run_once = mock_run_once
            mock_worker_class.return_value = mock_library_worker

            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Run job processing
            asyncio.run(worker._process_next_job())

            # Worker should be idle after processing
            assert worker.is_idle is True

    def test_published_capabilities_match_library(self, mock_broadcaster):
        """Test that published capabilities come from library's task registry."""
        from src.worker import ComputeWorker

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            # Library reports these task types
            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = [
                "image_resize",
                "image_conversion",
                "video_transcoding"
            ]
            mock_worker_class.return_value = mock_library_worker

            # Worker only requests image tasks
            worker = ComputeWorker(
                worker_id="test-worker",
                supported_tasks=["image_resize", "image_conversion"]
            )
            worker._publish_worker_capabilities()

            # Check published capabilities
            call_args = mock_broadcaster.publish_retained.call_args
            payload_str = call_args[0][1]
            payload = json.loads(payload_str)

            # Should only include requested tasks that are available
            assert "image_resize" in payload["capabilities"]
            assert "image_conversion" in payload["capabilities"]
            assert "video_transcoding" not in payload["capabilities"]

    @pytest.mark.skip(reason="Test uses old module discovery pattern - needs rewrite for library-based worker")
    def test_heartbeat_publishes_periodically(self, mock_broadcaster):
        """Test that heartbeat task publishes capabilities periodically."""
        pass

    @pytest.mark.skip(reason="Test uses old module discovery pattern - needs rewrite for library-based worker")
    def test_capabilities_include_all_active_tasks(self, mock_broadcaster):
        """Test that published capabilities include all active tasks."""
        pass

    @pytest.mark.skip(reason="Test uses old module discovery pattern - needs rewrite for library-based worker")
    def test_broadcaster_not_connected_skip_publish(self, mock_broadcaster):
        """Test that publish is skipped if broadcaster not connected."""
        pass

    @pytest.mark.skip(reason="Idle count tracking changed to simple boolean - this test needs rewrite")
    def test_idle_count_never_negative(self, mock_broadcaster):
        """Test that idle count never goes below zero."""
        pass

    @pytest.mark.skip(reason="Idle count tracking changed to simple boolean - this test needs rewrite")
    def test_idle_count_never_exceeds_max(self, mock_broadcaster):
        """Test that idle count never exceeds 1."""
        pass


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

    def test_clear_retained_method_exists(self):
        """Test that broadcaster has clear_retained method.

        Note: This test verifies that cl_server_shared.mqtt.MQTTBroadcaster
        has implemented the clear_retained method. If this test fails, it means
        the cl_server_shared package needs to be updated.
        """
        from cl_server_shared.mqtt import MQTTBroadcaster

        broadcaster = MQTTBroadcaster("localhost", 1883, "test/topic")

        # Skip test if clear_retained not yet implemented in cl_server_shared
        if not hasattr(broadcaster, "clear_retained"):
            pytest.skip("clear_retained method not yet implemented in cl_server_shared")

        assert callable(broadcaster.clear_retained)


class TestWorkerShutdown:
    """Tests for worker shutdown behavior."""

    @pytest.mark.asyncio
    async def test_clear_retained_called_on_shutdown(self):
        """Test that clear_retained is called when worker shuts down."""
        from src.worker import ComputeWorker, shutdown_event
        import asyncio

        mock_broadcaster = MagicMock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_retained.return_value = True
        mock_broadcaster.clear_retained = Mock(return_value=True)

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize"]

            # Make run_once async that returns False (no jobs)
            async def mock_run_once(task_types):
                # Set shutdown event after first poll to exit loop
                shutdown_event.set()
                return False

            mock_library_worker.run_once = mock_run_once
            mock_worker_class.return_value = mock_library_worker

            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Clear shutdown event before running
            shutdown_event.clear()

            # Run worker (will exit after first iteration due to shutdown_event)
            await worker.run()

            # Verify clear_retained was called
            assert mock_broadcaster.clear_retained.called
            call_args = mock_broadcaster.clear_retained.call_args
            topic = call_args[0][0]
            assert "test-worker" in topic

    def test_clear_worker_capabilities_method(self):
        """Test _clear_worker_capabilities method."""
        from src.worker import ComputeWorker

        mock_broadcaster = MagicMock()
        mock_broadcaster.connected = True
        mock_broadcaster.clear_retained = Mock(return_value=True)

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize"]
            mock_worker_class.return_value = mock_library_worker

            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Call clear method
            worker._clear_worker_capabilities()

            # Verify clear_retained was called with correct topic
            mock_broadcaster.clear_retained.assert_called_once()
            call_args = mock_broadcaster.clear_retained.call_args
            topic = call_args[0][0]
            assert topic == "inference/workers/test-worker"

    def test_clear_capabilities_not_connected(self):
        """Test that clear_capabilities handles broadcaster not connected."""
        from src.worker import ComputeWorker

        mock_broadcaster = MagicMock()
        mock_broadcaster.connected = False

        with patch("src.worker.get_broadcaster", return_value=mock_broadcaster), \
             patch("src.worker.Worker") as mock_worker_class, \
             patch("src.worker.SQLAlchemyJobRepository"):

            mock_library_worker = Mock()
            mock_library_worker.get_supported_task_types.return_value = ["image_resize"]
            mock_worker_class.return_value = mock_library_worker

            worker = ComputeWorker(worker_id="test-worker", supported_tasks=["image_resize"])

            # Should not raise exception
            worker._clear_worker_capabilities()

            # Verify clear_retained was not called
            assert not hasattr(mock_broadcaster, 'clear_retained') or \
                   not mock_broadcaster.clear_retained.called
