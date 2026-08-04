"""
Pytest configuration.

Sets up sys.path for all tests to find the app module.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path so app module can be found
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
