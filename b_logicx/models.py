"""Data models for B-Logicx events."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BLXEvent:
    """A decoded event from the B-Logicx bus."""

    command: str
    group: int
    address: int
    raw: bytes

    def __str__(self) -> str:
        return f"{self.command} {self.group}.{self.address}"

    @property
    def key(self) -> tuple[int, int]:
        """Unique key for this address (group, address)."""
        return (self.group, self.address)
