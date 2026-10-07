"""Decode multi-frame LDM / TSM measurements.

LDM light:
  Value g.a (g != 11) → light payload
  System G.A          → device id
  raw = (g<<8)|a ; percent = raw * 100 / 1024

The integer value measured in this way does not match the value
displayed in BLConfig completely, but it's close enough and certainly
yields a valid 'brightness' number that should be usable in HA

TSM (exactly three frames; anything after is ignored):
  Value 11.x          → measured °C = address/2 (offset included)
  Settings i.s        → preset i, setpoint s/2 °C
  System G.A          → device id → commit reading

Dual sticky Values: group 11 is TSM-only; other groups are LDM-only.

I currently have no other types of sensors to analyze.
FIXME: BL-WSM coming soon!
"""

from __future__ import annotations

from dataclasses import dataclass, field

# LDM request: fixed Data 0.2 then Select <device>
LDM_REQUEST_DATA_GROUP = 0
LDM_REQUEST_DATA_ADDRESS = 2

# TSM measured temperature uses Value group 11
TSM_VALUE_GROUP = 11

TSM_PRESET_NAMES = {
    1: "Night",
    2: "Day",
    3: "Away",
    4: "Holiday",
}

VALUE_MAX_AGE_S = 2.0


def packed12(group: int, address: int) -> int:
    """12-bit field: group nibble + address byte."""
    return ((int(group) & 0x0F) << 8) | (int(address) & 0xFF)


def value_frame_to_raw(group: int, address: int) -> int:
    """LDM light count: 12-bit packed field (group nibble + address)."""
    return packed12(group, address)


def raw_to_percent(raw: int) -> float:
    """LDM brightness percent (full scale 1024)."""
    return max(0.0, min(100.0, float(raw) * 100.0 / 1024.0))


def value_frame_to_percent(group: int, address: int) -> float:
    """LDM brightness, 0–100, from one Value frame that is not group 11."""
    return raw_to_percent(value_frame_to_raw(group, address))


def value11_to_temperature_c(address: int) -> float:
    """TSM measured temperature from Value 11.x (½ °C steps, offset included)."""
    return int(address) / 2.0


def settings_to_preset(group: int, address: int) -> tuple[int, float, str]:
    """Return (preset_index, setpoint_c, name)."""
    idx = int(group) & 0x0F
    setpoint = int(address) / 2.0
    name = TSM_PRESET_NAMES.get(idx, f"Preset {idx}")
    return idx, setpoint, name


@dataclass
class LdmReading:
    """One light reading. group and address are the System frame (the sensor).

    value_group and value_address are the Value frame that carried the light level.
    """

    group: int
    address: int
    raw: int
    percent: float
    value_group: int
    value_address: int


@dataclass
class TsmReading:
    """Result of a complete TSM triple (Value 11 + Settings + System id)."""

    group: int
    address: int
    temperature_c: float
    value_address: int | None = None
    preset_index: int | None = None
    preset_name: str | None = None
    preset_setpoint: float | None = None


@dataclass
class MeasureBusState:
    """Dual-sticky multi-frame decode (LDM Value ≠ TSM Value 11).

    TSM completes on the third frame (System device id) only.
    """

    ldm_value_raw: int | None = None
    ldm_value_group: int | None = None
    ldm_value_address: int | None = None
    ldm_value_at: float = 0.0

    tsm_temp_c: float | None = None
    tsm_value_address: int | None = None
    tsm_value_at: float = 0.0

    last_settings_index: int | None = None
    last_settings_setpoint: float | None = None
    last_settings_name: str | None = None
    last_settings_at: float = 0.0

    preset_setpoint_cache: dict[int, float] = field(default_factory=dict)

    def note_value(self, group: int, address: int, now: float) -> None:
        """Remember the latest Value. Group 11 is a temperature; any other group is light.

        A newer Value of the same kind replaces the previous one. This does not
        look at other commands, so an unrelated frame cannot wipe the slot.
        """
        g = int(group) & 0x0F
        a = int(address) & 0xFF
        if g == TSM_VALUE_GROUP:
            self.tsm_temp_c = value11_to_temperature_c(a)
            self.tsm_value_address = a
            self.tsm_value_at = now
        else:
            self.ldm_value_raw = value_frame_to_raw(g, a)
            self.ldm_value_group = g
            self.ldm_value_address = a
            self.ldm_value_at = now

    def note_settings(self, group: int, address: int, now: float) -> None:
        """Remember the latest thermostat preset. Group is the preset, address/2 is °C."""
        idx, sp, name = settings_to_preset(group, address)
        self.last_settings_index = idx
        self.last_settings_setpoint = sp
        self.last_settings_name = name
        self.last_settings_at = now
        self.preset_setpoint_cache[idx] = sp

    def try_ldm_reading(
        self,
        system_group: int,
        system_address: int,
        now: float,
        *,
        max_age: float = VALUE_MAX_AGE_S,
    ) -> LdmReading | None:
        """Pair a System frame with a light Value from the last 2 seconds.

        The Value is left in place, so a second System inside that window can
        pair with it too. A Value older than max_age is ignored, not deleted.
        """
        if self.ldm_value_raw is None or self.ldm_value_at <= 0:
            return None
        if now - self.ldm_value_at > max_age:
            return None
        assert self.ldm_value_group is not None
        assert self.ldm_value_address is not None
        return LdmReading(
            group=system_group,
            address=system_address,
            raw=self.ldm_value_raw,
            percent=raw_to_percent(self.ldm_value_raw),
            value_group=self.ldm_value_group,
            value_address=self.ldm_value_address,
        )

    def try_tsm_reading(
        self,
        system_group: int,
        system_address: int,
        now: float,
        *,
        max_age: float = VALUE_MAX_AGE_S,
    ) -> TsmReading | None:
        """Pair a System frame with a Value 11 from the last 2 seconds.

        The preset is whatever Settings was seen last, even if that was earlier
        than the 2 seconds. The Value is left in place.
        """
        if self.tsm_temp_c is None or self.tsm_value_at <= 0:
            return None
        if now - self.tsm_value_at > max_age:
            return None
        return TsmReading(
            group=system_group,
            address=system_address,
            temperature_c=self.tsm_temp_c,
            value_address=self.tsm_value_address,
            preset_index=self.last_settings_index,
            preset_name=self.last_settings_name,
            preset_setpoint=self.last_settings_setpoint,
        )
