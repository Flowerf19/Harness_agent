"""Test path setup for running native gateway tests from the repo root."""
from __future__ import annotations

import sys
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICES_ROOT))
