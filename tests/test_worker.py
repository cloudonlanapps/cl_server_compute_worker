"""Tests for worker module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.worker import discover_compute_modules, ensure_module_venv


def test_discover_compute_modules(tmp_path):
    """Test module discovery."""
    # Create mock module structure
    compute_modules_dir = tmp_path / "compute_modules"
    compute_modules_dir.mkdir()
    
    module_dir = compute_modules_dir / "test_module"
    module_dir.mkdir()
    (module_dir / "src").mkdir()
    (module_dir / "src" / "runner.py").touch()
    
    with open(module_dir / "pyproject.toml", "w") as f:
        f.write("""
[tool.compute_module]
supported_tasks = ["image_resize"]
""")
    
    with patch('src.worker.Path') as mock_path:
        mock_path.return_value.parent.parent = tmp_path
        mock_path.return_value.exists.return_value = True
        
        # Call the function
        from src.worker import discover_compute_modules
        registry = discover_compute_modules()
        
        assert "image_resize" in registry
        assert registry["image_resize"]["module_name"] == "test_module"
        assert registry["image_resize"]["runner_path"].name == "runner.py"

def test_discover_compute_modules_conflict(tmp_path):
    """Test module discovery conflict detection."""
    compute_modules_dir = tmp_path / "compute_modules"
    compute_modules_dir.mkdir()

    # Create two modules claiming the same task
    module1_dir = compute_modules_dir / "module1"
    module1_dir.mkdir()
    (module1_dir / "src").mkdir()
    (module1_dir / "src" / "runner.py").touch()
    with open(module1_dir / "pyproject.toml", "w") as f:
        f.write('[tool.compute_module]\nsupported_tasks = ["task_a"]')

    module2_dir = compute_modules_dir / "module2"
    module2_dir.mkdir()
    (module2_dir / "src").mkdir()
    (module2_dir / "src" / "runner.py").touch()
    with open(module2_dir / "pyproject.toml", "w") as f:
        f.write('[tool.compute_module]\nsupported_tasks = ["task_a"]')

    with patch('src.worker.Path') as mock_path:
        mock_path.return_value.parent.parent = tmp_path
        mock_path.return_value.exists.return_value = True
        
        from src.worker import discover_compute_modules
        
        with pytest.raises(ValueError, match="Conflict detected"):
            discover_compute_modules()


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
    
    with patch('subprocess.run') as mock_run:
        result = ensure_module_venv(module_info)
        assert result is True



def test_worker_initialization():
    """Test worker initialization."""
    from src.worker import ComputeWorker
    
    with patch('src.worker.get_broadcaster') as mock_broadcaster:
        worker = ComputeWorker(
            worker_id="test-worker",
            supported_tasks=["image_resize"]
        )
    
    assert worker.worker_id == "test-worker"
    assert "image_resize" in worker.supported_tasks



# Add more worker tests here
