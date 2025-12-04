"""Pytest configuration for compute worker tests."""

import sys
from pathlib import Path

# Add src directory to path so modules can be imported
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
