"""Decode multi-frame LDM / TSM measurements (pure, no HA).

LDM light:
  Value g.a (g != 11) → light payload
  System G.A          → device id
  raw = ((g<<8)|a) - 3 ; percent = raw * 100 / 1024

TSM thermostat burst:
  Value 11.x          → measured °C = address/2 (offset included)
  Settings i.s        → preset i, setpoint s/2 °C
  System G.A          → device id → commit temp from sticky Value 11
  Data 0.26           → fixed marker (not temperature)
  Select G.A          → handshake
  System 15.16/48     → heat requested no/yes

Dual sticky Values: group 11 is TSM-only; other groups are LDM-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# LDM request: fixed Data 0.2 then Select <device>
LDM_REQUEST_DATA_GROUP = 0
LDM_REQUEST_DATA_ADDRESS = 2

# TSM measured temperature uses Value group 11
TSM_VALUE_GROUP = 11

# Heat requested (not plant on/off)
HEAT_REQUESTED_GROUP = 15
HEAT_REQUESTED_OFF_ADDRESS = 16
HEAT_REQUESTED_ON_ADDRESS = 48

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
    """LDM light count: packed − 3 (count+3 on the wire)."""
    return packed12(group, address) - 3


def raw_to_percent(raw: int) -> float:
    """LDM brightness percent (full scale 1024)."""
    return max(0.0, min(100.0, float(raw) * 100.0 / 1024.0))


def value_frame_to_percent(group: int, address: int) -> float:
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


def heat_requested_from_system(group: int, address: int) -> bool | None:
    """True/False if System 15.16/15.48, else None."""
    if int(group) != HEAT_REQUESTED_GROUP:
        return None
    if int(address) == HEAT_REQUESTED_ON_ADDRESS:
        return True
    if int(address) == HEAT_REQUESTED_OFF_ADDRESS:
        return False
    return None


@dataclass
class LdmReading:
    group: int
    address: int
    raw: int
    percent: float
    value_group: int
    value_address: int


@dataclass
class TsmReading:
    group: int
    address: int
    temperature_c: float | None = None  # None = do not update temp entity
    value_address: int | None = None
    preset_index: int | None = None
    preset_name: str | None = None
    preset_setpoint: float | None = None
    heat_requested: bool | None = None


@dataclass
class MeasureBusState:
    """Dual-sticky multi-frame decode (LDM Value ≠ TSM Value 11)."""

    # LDM: last Value with group != 11
    ldm_value_raw: int | None = None
    ldm_value_group: int | None = None
    ldm_value_address: int | None = None
    ldm_value_at: float = 0.0

    # TSM: last Value with group == 11
    tsm_temp_c: float | None = None
    tsm_value_address: int | None = None
    tsm_value_at: float = 0.0

    last_settings_index: int | None = None
    last_settings_setpoint: float | None = None
    last_settings_name: str | None = None
    last_settings_at: float = 0.0

    preset_setpoint_cache: dict[int, float] = field(default_factory=dict)

    def note_value(self, group: int, address: int, now: float) -> None:
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
        heat: bool | None = None,
    ) -> TsmReading | None:
        """Commit TSM reading from sticky Value 11 temp + optional Settings/heat."""
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
            heat_requested=heat,
        )

    def heat_only_reading(
        self,
        system_group: int,
        system_address: int,
        heat: bool,
    ) -> TsmReading:
        """Heat-requested update; temperature_c left None so entities keep last."""
        return TsmReading(
            group=system_group,
            address=system_address,
            temperature_c=None,
            value_address=self.tsm_value_address,
            preset_index=self.last_settings_index,
            preset_name=self.last_settings_name,
            preset_setpoint=self.last_settings_setpoint,
            heat_requested=heat,
        )
