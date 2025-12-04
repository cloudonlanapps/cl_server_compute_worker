"""Pytest configuration for compute worker tests."""

import sys
from pathlib import Path

# Add the parent directory (project root) to Python path so 'src' can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
