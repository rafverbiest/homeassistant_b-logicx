"""Human-readable B-Logicx bus lines (shared by blxmonitor and tests).

Format matches blxmonitor.py:

  [HH:MM:SS.mmm] Set 2.80
  [HH:MM:SS.mmm] [SENT] Status 2.17
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import BLXEvent


def timestamp() -> str:
    """Return current wall time as HH:MM:SS.mmm."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def format_event(event: BLXEvent | str) -> str:
    """Right-hand side of a bus line: ``Set 2.80``."""
    return str(event)


def format_recv(event: BLXEvent | str, *, ts: str | None = None) -> str:
    """Gateway → client (live bus event), blxmonitor style."""
    if ts is None:
        ts = timestamp()
    return f"[{ts}] {format_event(event)}"


def format_sent(event: BLXEvent | str, *, ts: str | None = None) -> str:
    """Client → gateway (command we sent), blxmonitor ``[SENT]`` style."""
    if ts is None:
        ts = timestamp()
    return f"[{ts}] [SENT] {format_event(event)}"
