"""Pytest configuration for image_resize tests."""

import sys
from pathlib import Path

# Add src directory to path so modules can be imported
# First remove any conflicting compute module paths
image_conversion_src = Path(__file__).parent.parent.parent / "image_conversion" / "src"
if str(image_conversion_src) in sys.path:
    sys.path.remove(str(image_conversion_src))

# Remove any other compute module src paths that may have been added
for path in list(sys.path):
    if "compute_modules" in path and "image_resize" not in path and path.endswith("src"):
        sys.path.remove(path)

# Now add our src
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Make sure this test session only uses local imports
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_image_resize_path():
    """Ensure image_resize imports use local src."""
    src_dir = Path(__file__).parent.parent / "src"
    image_conversion_src = Path(__file__).parent.parent.parent / "image_conversion" / "src"

    # Remove conflicting paths
    if str(image_conversion_src) in sys.path:
        sys.path.remove(str(image_conversion_src))

    # Move to front of sys.path if not already there
    if str(src_dir) in sys.path:
        sys.path.remove(str(src_dir))
    sys.path.insert(0, str(src_dir))
