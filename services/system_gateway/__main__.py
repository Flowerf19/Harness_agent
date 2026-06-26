"""Command-line entrypoint for the System Gateway service."""
from __future__ import annotations

import sys

from .cli.main import main


if __name__ == "__main__":
    sys.exit(main())
