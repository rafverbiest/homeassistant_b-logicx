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
# After the first frame, stay armed this long. A cover press is a Set on the
# relay we asked for and a Reset on the other one, and the Reset can arrive first.
DETECT_SETTLE_S = 0.5

_SET_RESET = frozenset({"Set", "Reset"})


def detect_match(
    command: str,
    group: int,
    address: int,
    known: set[tuple[int, int]],
    *,
    own_echo: bool = False,
    set_only: bool = False,
) -> bool:
    """True when this frame is a new Set or Reset the detect screen should keep.

    set_only is the cover listen: the direction we asked for answers with Set.
    Reset is the other relay and does not count.
    """
    if own_echo:
        return False
    if set_only:
        if command != "Set":
            return False
    elif command not in _SET_RESET:
        return False
    return (group, address) not in known


def shown_detect_frame(
    frames: list[tuple[int, int, bool]],
) -> tuple[int, int, bool] | None:
    """The address to show: a Set from this press, or the first frame if there was none."""
    for frame in frames:
        if frame[2]:
            return frame
    if not frames:
        return None
    return frames[0]


def remember_detect_partner(
    stash: tuple[int, int, bool] | None,
    command: str,
    group: int,
    address: int,
    known: set[tuple[int, int]],
    *,
    own_echo: bool = False,
) -> tuple[int, int, bool] | None:
    """Keep a later Set from the same press when the waiter already took the first frame.

    A stored Reset gives way to a Set. A stored Set stays.
    """
    if own_echo or command not in _SET_RESET:
        return stash
    if (group, address) in known:
        return stash
    frame = (group, address, command == "Set")
    if stash is None or (frame[2] and not stash[2]):
        return frame
    return stash


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
