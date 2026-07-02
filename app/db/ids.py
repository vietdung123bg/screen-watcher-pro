"""UUIDv7 generator (time-ordered UUID) for primary keys.

Why v7 (not v4): the first 48 bits are a millisecond timestamp, so newly minted
ids are monotonically increasing. That keeps SQLite's B-tree index append-friendly
(no random inserts / page splits like v4), giving insert & range-scan performance
close to an autoincrement integer while staying globally unique. Stored as the
canonical 36-char TEXT form for easy FK/JSON handling.

Python 3.11 has no uuid.uuid7(), so we build it per RFC 9562 §5.7.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> str:
    """Return a new time-ordered UUIDv7 as a canonical string."""
    unix_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = os.urandom(10)
    b = bytearray(16)
    b[0] = (unix_ms >> 40) & 0xFF
    b[1] = (unix_ms >> 32) & 0xFF
    b[2] = (unix_ms >> 24) & 0xFF
    b[3] = (unix_ms >> 16) & 0xFF
    b[4] = (unix_ms >> 8) & 0xFF
    b[5] = unix_ms & 0xFF
    b[6] = 0x70 | (rand[0] & 0x0F)      # version 7 in the high nibble
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)      # RFC 4122 variant (10xx)
    b[9:] = rand[3:]
    return str(uuid.UUID(bytes=bytes(b)))
