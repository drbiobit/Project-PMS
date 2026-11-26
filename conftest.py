"""Root conftest — put the repo root on sys.path so tests can import
`common`, `app`, and `build_index` directly (they live in the repo root,
not in a package)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
