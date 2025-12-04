"""Pytest configuration for image_conversion tests."""

import sys
from pathlib import Path

# Add src directory to path so modules can be imported
# Insert at the beginning of sys.path for this specific test
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Make sure this test session only uses local imports
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_image_conversion_path():
    """Ensure image_conversion imports use local src."""
    src_dir = Path(__file__).parent.parent / "src"
    # Move to front of sys.path if not already there
    if str(src_dir) in sys.path:
        sys.path.remove(str(src_dir))
    sys.path.insert(0, str(src_dir))
