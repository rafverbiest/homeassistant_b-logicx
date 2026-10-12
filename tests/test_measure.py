"""LDM / TSM codec and dual-sticky pairing (no Home Assistant)."""

from __future__ import annotations

import time

from b_logicx.measure import (
    MeasureBusState,
    raw_to_percent,
    settings_to_preset,
    value11_to_temperature_c,
    WSM_QUIET_ASK_AFTER_S,
    value14_to_kmh,
    value_frame_to_percent,
    value_frame_to_raw,
    wsm_should_confirm_quiet,
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


def test_ldm_counts_zero_and_full_scale():
    # 0 is Value 0.0. 1024, full scale, is Value 4.0.
    assert value_frame_to_raw(0, 0) == 0
    assert value_frame_to_raw(4, 0) == 1024
    assert raw_to_percent(0) == 0
    assert raw_to_percent(1024) == 100
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(0, 0, now)
    zero = st.try_ldm_reading(1, 23, now + 0.1)
    assert zero is not None and zero.raw == 0
    st.note_value(4, 0, now + 0.2)
    full = st.try_ldm_reading(1, 23, now + 0.3)
    assert full is not None and full.raw == 1024


def test_wsm_quiet_breeze_is_asked_again_and_calm_is_not():
    assert wsm_should_confirm_quiet(None, WSM_QUIET_ASK_AFTER_S) is False
    assert wsm_should_confirm_quiet(0, WSM_QUIET_ASK_AFTER_S) is False
    assert wsm_should_confirm_quiet(1, WSM_QUIET_ASK_AFTER_S - 1) is False
    assert wsm_should_confirm_quiet(1, WSM_QUIET_ASK_AFTER_S) is True
    assert wsm_should_confirm_quiet(2, WSM_QUIET_ASK_AFTER_S) is True
    assert wsm_should_confirm_quiet(3, WSM_QUIET_ASK_AFTER_S) is False
    assert wsm_should_confirm_quiet(25, 24 * 60 * 60) is False


def test_wsm_kmh_drops_halves():
    assert value14_to_kmh(0) == 0
    assert value14_to_kmh(1) == 0
    assert value14_to_kmh(2) == 1
    assert value14_to_kmh(50) == 25
    assert value14_to_kmh(99) == 49
    assert value14_to_kmh(100) == 50


def test_wsm_pairs_value_14_and_leaves_light_alone():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(3, 211, now)
    st.note_value(14, 50, now + 0.01)
    wind = st.try_wsm_reading(1, 12, now + 0.02)
    light = st.try_ldm_reading(1, 23, now + 0.03)
    assert wind is not None and wind.raw == 50 and wind.kmh == 25
    assert wind.group == 1 and wind.address == 12
    assert light is not None and light.raw == 979


def test_wsm_value_does_not_become_light_and_light_does_not_become_wind():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(14, 40, now)
    assert st.try_ldm_reading(1, 23, now + 0.1) is None
    assert st.try_wsm_reading(1, 12, now + 0.1).raw == 40
    st.note_value(3, 211, now + 0.2)
    assert st.try_wsm_reading(1, 12, now + 0.3).raw == 40
    assert st.try_ldm_reading(1, 23, now + 0.3).raw == 979


def test_wsm_ignores_address_above_100_and_keeps_zero():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(14, 101, now)
    assert st.wsm_raw is None
    assert st.try_wsm_reading(1, 12, now + 0.1) is None
    assert st.try_ldm_reading(1, 23, now + 0.1) is None
    st.note_value(14, 0, now + 0.2)
    calm = st.try_wsm_reading(1, 12, now + 0.3)
    assert calm is not None and calm.raw == 0 and calm.kmh == 0
    st.note_value(14, 1, now + 0.4)
    assert st.try_wsm_reading(1, 12, now + 0.5).kmh == 0


def test_wsm_stale_value_is_ignored_and_not_deleted():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(14, 50, now)
    assert st.try_wsm_reading(1, 12, now + 5.0, max_age=2.0) is None
    assert st.wsm_raw == 50


def test_wsm_temperature_and_wind_stay_separate():
    st = MeasureBusState()
    now = time.monotonic()
    st.note_value(11, 48, now)
    st.note_value(14, 100, now + 0.01)
    assert st.try_tsm_reading(1, 45, now + 0.02).temperature_c == 24.0
    assert st.try_wsm_reading(1, 12, now + 0.02).kmh == 50
    assert st.try_ldm_reading(1, 23, now + 0.02) is None
