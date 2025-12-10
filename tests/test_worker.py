"""Tests for worker module using cl_ml_tools library.

Tests verify that the worker correctly integrates with cl_ml_tools
and handles job processing, MQTT capabilities, and error cases.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import asyncio


class TestWorkerInitialization:
    """Test worker initialization with cl_ml_tools."""

    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    def test_worker_initialization(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test that worker initializes with library Worker."""
        from src.worker import ComputeWorker

        # Mock library worker
        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = [
            "image_resize",
            "image_conversion",
        ]
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=["image_resize"]
        )

        assert worker.worker_id == "test-worker"
        assert worker.requested_tasks == ["image_resize"]
        assert "image_resize" in worker.active_tasks
        assert "image_conversion" not in worker.active_tasks  # Not requested

    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    def test_worker_initialization_all_tasks(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test that worker with None supported_tasks accepts all available."""
        from src.worker import ComputeWorker

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = [
            "image_resize",
            "image_conversion",
        ]
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=None  # Accept all
        )

        assert "image_resize" in worker.active_tasks
        assert "image_conversion" in worker.active_tasks

    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    def test_worker_no_matching_tasks(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test worker with no matching tasks."""
        from src.worker import ComputeWorker

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = ["image_resize"]
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker",
            supported_tasks=["video_processing"],  # Not available
        )

        assert len(worker.active_tasks) == 0


class TestWorkerJobProcessing:
    """Test job processing with cl_ml_tools Worker."""

    @pytest.mark.asyncio
    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    async def test_process_job_success(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test successful job processing."""
        from src.worker import ComputeWorker

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = ["image_resize"]

        # Make run_once async
        async def mock_run_once(task_types):
            return True

        mock_library_worker.run_once = mock_run_once
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=["image_resize"]
        )

        result = await worker._process_next_job()

        assert result is True
        assert worker.is_idle is True  # Should be idle after processing

    @pytest.mark.asyncio
    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    async def test_process_no_job_available(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test behavior when no jobs are available."""
        from src.worker import ComputeWorker

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = ["image_resize"]

        # Make run_once async
        async def mock_run_once(task_types):
            return False  # No job available

        mock_library_worker.run_once = mock_run_once
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=["image_resize"]
        )

        result = await worker._process_next_job()

        assert result is False
        assert worker.is_idle is True

    @pytest.mark.asyncio
    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    async def test_process_job_exception(
        self, mock_repo, mock_broadcaster, mock_worker_class
    ):
        """Test job processing with exception."""
        from src.worker import ComputeWorker

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = ["image_resize"]

        # Make run_once async that raises exception
        async def mock_run_once(task_types):
            raise RuntimeError("Test error")

        mock_library_worker.run_once = mock_run_once
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=["image_resize"]
        )

        result = await worker._process_next_job()

        assert result is False  # Should return False on exception
        assert worker.is_idle is True  # Should still mark as idle


class TestWorkerCapabilities:
    """Test MQTT capability publishing."""

    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    def test_publish_capabilities(
        self, mock_repo, mock_broadcaster_func, mock_worker_class
    ):
        """Test capability publishing to MQTT."""
        from src.worker import ComputeWorker

        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_retained = Mock(return_value=True)
        mock_broadcaster_func.return_value = mock_broadcaster

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = [
            "image_resize",
            "image_conversion",
        ]
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker",
            supported_tasks=["image_resize", "image_conversion"],
        )

        worker._publish_worker_capabilities()

        # Verify publish was called
        mock_broadcaster.publish_retained.assert_called_once()
        call_args = mock_broadcaster.publish_retained.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert "test-worker" in topic
        assert "image_resize" in payload
        assert "image_conversion" in payload
        assert "idle_count" in payload

    @patch("src.worker.Worker")
    @patch("src.worker.get_broadcaster")
    @patch("src.worker.SQLAlchemyJobRepository")
    def test_publish_capabilities_not_connected(
        self, mock_repo, mock_broadcaster_func, mock_worker_class
    ):
        """Test capability publishing when MQTT not connected."""
        from src.worker import ComputeWorker

        mock_broadcaster = Mock()
        mock_broadcaster.connected = False
        mock_broadcaster_func.return_value = mock_broadcaster

        mock_library_worker = Mock()
        mock_library_worker.get_supported_task_types.return_value = ["image_resize"]
        mock_worker_class.return_value = mock_library_worker

        worker = ComputeWorker(
            worker_id="test-worker", supported_tasks=["image_resize"]
        )

        # Should not raise exception
        worker._publish_worker_capabilities()

        # Verify publish_retained was not called
        mock_broadcaster.publish_retained.assert_not_called()
