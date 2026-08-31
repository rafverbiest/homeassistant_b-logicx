"""B-Logicx async library.

Reusable library for communicating with B-Logicx BL-NWM gateways.
Can be used from command-line tools as well as Home Assistant.

By default, Program datagrams and the two following ones are filtered
(see BLXConnection.skip_programming).
"""

from .connection import BLXConnection, BLXConnectionError
from .const import BLX_TCP_PORT, COMMAND_CODES, COMMAND_NAMES
from .models import BLXEvent
from .protocol import decode_datagram, encode_datagram
from .rtc import build_rtc_sync_frames, build_rtc_sync_raw, next_phased_sync

__all__ = [
    "BLXConnection",
    "BLXConnectionError",
    "BLXEvent",
    "BLX_TCP_PORT",
    "COMMAND_CODES",
    "COMMAND_NAMES",
    "encode_datagram",
    "decode_datagram",
    "build_rtc_sync_frames",
    "build_rtc_sync_raw",
    "next_phased_sync",
]
