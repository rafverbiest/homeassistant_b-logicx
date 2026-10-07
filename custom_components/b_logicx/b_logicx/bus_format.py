"""Text lines for the bus log. This is not the wire format.

A frame heard from the gateway is just the event. A frame this program
sent is the same line with [SENT] in front, so the two directions stay
apart in one log:

  [YYYY-MM-DD HH:MM:SS.mmm] Set 2.80
  [YYYY-MM-DD HH:MM:SS.mmm] [SENT] Status 2.17
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import BLXEvent


def timestamp() -> str:
    """Local clock as YYYY-MM-DD HH:MM:SS.mmm."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def format_event(event: BLXEvent | str) -> str:
    """The event itself: "Set 2.80". A BLXEvent uses its own text form."""
    return str(event)


def format_recv(event: BLXEvent | str, *, ts: str | None = None) -> str:
    """One log line for a datagram received from the gateway."""
    if ts is None:
        ts = timestamp()
    return f"[{ts}] {format_event(event)}"


def format_sent(event: BLXEvent | str, *, ts: str | None = None) -> str:
    """One log line for a datagram this program sent to the gateway."""
    if ts is None:
        ts = timestamp()
    return f"[{ts}] [SENT] {format_event(event)}"
