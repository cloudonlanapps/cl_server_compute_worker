"""Tests for SQLAlchemyJobRepository MQTT broadcasting from cl_server_shared.

These tests verify that the SQLAlchemyJobRepository from cl_server_shared
has the MQTT broadcasting functionality for job progress updates.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from cl_server_shared.adapters import SQLAlchemyJobRepository


class TestSQLAlchemyJobRepositoryBroadcasting:
    """Tests for MQTT broadcasting in SQLAlchemyJobRepository from cl_server_shared."""

    def _create_mock_session_factory(self, rowcount=1):
        """Helper method to create properly mocked session factory."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = rowcount
        mock_session.execute.return_value = mock_result

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=False)

        return mock_session_factory

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_broadcaster_initialized(self, mock_get_broadcaster):
        """Test that broadcaster is initialized in __init__."""
        mock_broadcaster = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster
        mock_session_factory = Mock()

        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Verify broadcaster was created
        assert hasattr(repository, 'broadcaster'), "SQLAlchemyJobRepository should have broadcaster attribute"
        assert repository.broadcaster is not None

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_update_job_broadcasts_progress(self, mock_get_broadcaster):
        """Test that update_job broadcasts progress when progress is updated."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory(rowcount=1)
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job with progress
        job_id = "test-job-123"
        repository.update_job(job_id, progress=50.0, status="processing")

        # Verify publish_event was called with correct parameters
        mock_broadcaster.publish_event.assert_called_once_with(
            "processing", job_id, {"progress": 50.0}
        )

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_update_job_broadcasts_with_default_status(self, mock_get_broadcaster):
        """Test that update_job uses default status 'processing' when status not provided."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory(rowcount=1)
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job with only progress (no status)
        job_id = "test-job-123"
        repository.update_job(job_id, progress=75.0)

        # Verify publish_event was called with default status
        mock_broadcaster.publish_event.assert_called_once_with(
            "processing", job_id, {"progress": 75.0}
        )

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_update_job_no_broadcast_without_progress(self, mock_get_broadcaster):
        """Test that update_job does not broadcast when progress is not updated."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory(rowcount=1)
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job without progress
        repository.update_job("test-job-123", status="completed")

        # Verify publish_event was NOT called
        mock_broadcaster.publish_event.assert_not_called()

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_update_job_no_broadcast_when_not_connected(self, mock_get_broadcaster):
        """Test that update_job does not broadcast when broadcaster is not connected."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = False
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory(rowcount=1)
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job with progress
        repository.update_job("test-job-123", progress=50.0, status="processing")

        # Verify publish_event was NOT called (broadcaster not connected)
        mock_broadcaster.publish_event.assert_not_called()

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_update_job_no_broadcast_when_update_fails(self, mock_get_broadcaster):
        """Test that update_job does not broadcast when database update fails."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory(rowcount=0)
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job with progress (but update will fail)
        repository.update_job("nonexistent-job", progress=50.0)

        # Verify publish_event was NOT called
        mock_broadcaster.publish_event.assert_not_called()

    @patch("cl_server_shared.adapters.get_broadcaster")
    def test_broadcast_progress_with_various_statuses(self, mock_get_broadcaster):
        """Test that broadcast works with different job statuses."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        repository = SQLAlchemyJobRepository(
            self._create_mock_session_factory(rowcount=1)
        )

        # Test different statuses
        statuses = ["processing", "completed", "error"]
        for status in statuses:
            mock_broadcaster.publish_event.reset_mock()

            # Create new session factory for each iteration
            mock_session_factory = self._create_mock_session_factory(rowcount=1)
            repository.session_factory = mock_session_factory

            repository.update_job("test-job", progress=100.0, status=status)

            mock_broadcaster.publish_event.assert_called_once_with(
                status, "test-job", {"progress": 100.0}
            )
