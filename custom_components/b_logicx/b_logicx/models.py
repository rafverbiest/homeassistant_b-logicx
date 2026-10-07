"""One decoded datagram.

After the two wire bytes are split, the rest of the program sees a command
name, a group (0–15) and an address (0–255). The printed form is "Set 2.80"
to match the bus monitor in BLConfig.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BLXEvent:
    """Command name, group and address from one 2-byte datagram."""

    command: str
    group: int
    address: int
    raw: bytes

    def __str__(self) -> str:
        """Log form: command, then group.address. Example: Set 2.80."""
        return f"{self.command} {self.group}.{self.address}"

    @property
    def key(self) -> tuple[int, int]:
        """(group, address). Entities register on this pair."""
        return (self.group, self.address)
