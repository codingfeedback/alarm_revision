from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEPENDENCY_DIRS = [
    BASE_DIR / "vendor_lib",
    BASE_DIR / "deps",
]

for dependency_dir in DEPENDENCY_DIRS:
    if dependency_dir.exists() and str(dependency_dir) not in sys.path:
        sys.path.insert(0, str(dependency_dir))
