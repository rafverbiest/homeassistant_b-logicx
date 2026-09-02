"""LDM / TSM codec and dual-sticky pairing (no Home Assistant)."""

from __future__ import annotations

import time

from b_logicx.measure import (
    MeasureBusState,
    raw_to_percent,
    settings_to_preset,
    value11_to_temperature_c,
    value_frame_to_percent,
    value_frame_to_raw,
)


def test_ldm_codec_known_samples():
    # raw = packed = (g<<8)|a  (no −3); percent = raw*100/1024
    assert value_frame_to_raw(0, 14) == 14
    assert abs(value_frame_to_percent(0, 14) - 1.3671875) < 0.001  # ~1.37%
    assert value_frame_to_raw(3, 49) == 817
    assert abs(value_frame_to_percent(3, 49) - 79.78515625) < 0.001  # ~79.79%
    assert value_frame_to_raw(3, 218) == 986
    assert abs(value_frame_to_percent(3, 218) - 96.2890625) < 0.001
    assert value_frame_to_raw(3, 243) == 1011
    assert abs(raw_to_percent(1011) - 98.73046875) < 0.001
    assert value_frame_to_raw(3, 211) == 979


def test_tsm_value11_temperature():
    assert value11_to_temperature_c(48) == 24.0
    assert value11_to_temperature_c(47) == 23.5
    assert value11_to_temperature_c(46) == 23.0


def test_settings_preset():
    idx, sp, name = settings_to_preset(1, 34)
    assert idx == 1 and sp == 17.0 and name == "Night"
    idx, sp, name = settings_to_preset(2, 45)
    assert idx == 2 and sp == 22.5 and name == "Day"


def test_ldm_sticky_pairing():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(3, 211, now)
    reading = st.try_ldm_reading(1, 23, now + 0.1)
    assert reading is not None
    assert reading.raw == 979  # Value 3.211
    assert reading.group == 1 and reading.address == 23


def test_ldm_ignores_value11():
    """TSM Value 11.x must not become LDM light payload."""
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(11, 48, now)
    assert st.try_ldm_reading(1, 23, now + 0.1) is None


def test_tsm_ignores_ldm_value():
    """LDM Value 3.x must not become TSM temperature."""
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(3, 211, now)
    assert st.try_tsm_reading(1, 45, now + 0.1) is None


def test_tsm_triple_only():
    """Complete TSM with Value + Settings + System — no trailing frames."""
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(11, 48, now)
    st.note_settings(1, 34, now + 0.01)
    reading = st.try_tsm_reading(1, 45, now + 0.02)
    assert reading is not None
    assert reading.temperature_c == 24.0
    assert reading.preset_name == "Night"
    assert reading.preset_setpoint == 17.0


def test_interleaved_ldm_tsm_both_correct():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(3, 211, now)
    st.note_value(11, 48, now + 0.01)
    st.note_settings(2, 44, now + 0.02)
    ldm = st.try_ldm_reading(1, 23, now + 0.03)
    tsm = st.try_tsm_reading(1, 45, now + 0.04)
    assert ldm is not None and ldm.raw == 979
    assert tsm is not None and tsm.temperature_c == 24.0
    assert tsm.preset_name == "Day"


def test_interleaved_reverse_value_order():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(11, 46, now)  # 23.0 °C
    st.note_value(3, 243, now + 0.01)  # LDM 1011
    tsm = st.try_tsm_reading(1, 45, now + 0.02)
    ldm = st.try_ldm_reading(1, 23, now + 0.03)
    assert tsm is not None and tsm.temperature_c == 23.0
    assert ldm is not None and ldm.raw == 1011


def test_ldm_stale_value():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(3, 211, now)
    assert st.try_ldm_reading(1, 23, now + 5.0, max_age=2.0) is None


def test_tsm_mid_burst_ldm_does_not_clobber_tsm_sticky():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(11, 48, now)
    st.note_settings(1, 34, now + 0.01)
    st.note_value(3, 211, now + 0.02)
    ldm = st.try_ldm_reading(1, 23, now + 0.03)
    tsm = st.try_tsm_reading(1, 45, now + 0.04)
    assert ldm is not None and ldm.raw == 979
    assert tsm is not None and tsm.temperature_c == 24.0
