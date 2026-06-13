"""Constants for T2 timeline memory."""
from __future__ import annotations

import os


EMBEDDING_DIM = int(os.getenv("EMBEDDING_VECTOR_SIZE", "1024"))
TTL_BY_IMPORTANCE = {5: 90, 4: 60, 3: 30, 2: 14, 1: 7}
MAX_CATALOGS_PER_MEMORY = 2
KNN_NEIGHBOURS_FOR_PRE_FLIGHT = 5
