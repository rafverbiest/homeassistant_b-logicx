"""Which Set or Reset a detect screen should keep.

Any group counts. Group 2 and group 10 are only the usual RLM and SoftM
examples, not a filter. A frame this integration just sent for a SoftM,
and any address already saved, are left for the normal handlers.
"""

from __future__ import annotations

try:
    from ..const import ADDRESS_TYPE_SHUTTER
except ImportError:  # tests import this package as top-level b_logicx
    from const import ADDRESS_TYPE_SHUTTER

# The options dialog stops waiting after this long.
DETECT_WAIT_S = 30

_SET_RESET = frozenset({"Set", "Reset"})


def detect_match(
    command: str,
    group: int,
    address: int,
    known: set[tuple[int, int]],
    *,
    own_echo: bool = False,
) -> bool:
    """True when this frame is a new Set or Reset the detect screen should keep."""
    if own_echo:
        return False
    if command not in _SET_RESET:
        return False
    return (group, address) not in known


def _pair(entry: dict, group_key: str, address_key: str) -> tuple[int, int] | None:
    group = entry.get(group_key)
    address = entry.get(address_key)
    if isinstance(group, bool) or isinstance(address, bool):
        return None
    if isinstance(group, int) and isinstance(address, int):
        return (group, address)
    return None


def configured_bus_keys(addresses: list[dict]) -> set[tuple[int, int]]:
    """Every bus pair already saved, including both relays of a cover.

    A Sfeer room has no address of its own. Each mood does.
    """
    keys: set[tuple[int, int]] = set()
    for entry in addresses:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == ADDRESS_TYPE_SHUTTER:
            for group_key, address_key in (
                ("open_group", "open_address"),
                ("close_group", "close_address"),
            ):
                pair = _pair(entry, group_key, address_key)
                if pair is not None:
                    keys.add(pair)
            continue
        pair = _pair(entry, "group", "address")
        if pair is not None:
            keys.add(pair)
        for mood in entry.get("moods") or []:
            if isinstance(mood, dict):
                mood_pair = _pair(mood, "group", "address")
                if mood_pair is not None:
                    keys.add(mood_pair)
    return keys
