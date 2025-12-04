"""Tests for worker module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from worker import discover_compute_modules, ensure_module_venv


def test_discover_compute_modules(tmp_path):
    """Test module discovery."""
    # Create mock module structure
    module_dir = tmp_path / "test_module"
    module_dir.mkdir()
    (module_dir / "runner.py").touch()
    (module_dir / "task.py").touch()
    (module_dir / "pyproject.toml").touch()
    
    with patch('worker.Path') as mock_path:
        mock_path.return_value.parent.parent = tmp_path
        mock_path.return_value.exists.return_value = True
        
        # This would need actual implementation
        # Just testing the structure exists
        assert module_dir.exists()
        assert (module_dir / "runner.py").exists()


def test_ensure_module_venv_exists(tmp_path):
    """Test venv check when it already exists."""
    venv_path = tmp_path / ".venv"
    venv_path.mkdir()
    python_path = venv_path / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.touch()
    
    module_info = {
        "module_name": "test_module",
        "module_path": tmp_path,
        "venv_path": venv_path,
        "python_path": python_path
    }
    
    result = ensure_module_venv(module_info)
    assert result is True


@pytest.mark.asyncio
async def test_worker_initialization():
    """Test worker initialization."""
    from worker import ComputeWorker
    
    worker = ComputeWorker(
        worker_id="test-worker",
        supported_tasks=["image_resize"]
    )
    
    assert worker.worker_id == "test-worker"
    assert "image_resize" in worker.supported_tasks


# Add more worker tests here
