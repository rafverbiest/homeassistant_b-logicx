"""Which registered devices still belong to the saved address list."""

from const import (
    ADDRESS_TYPE_AUD,
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_READONLY,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    ADDRESS_TYPE_SOFTM,
    ADDRESS_TYPE_TSM,
    DOMAIN,
    address_device,
    configured_device_identifiers,
    device_no_longer_configured,
    get_cover_device_identifiers,
    get_device_identifiers,
    get_sfeer_device_identifiers,
)

HOST = "192.168.1.10"


def test_address_device_matches_the_per_type_identifiers():
    rlm = {"type": "rlm", "name": "Hall", "group": 2, "address": 80}
    assert address_device(HOST, rlm)[0] == get_device_identifiers(HOST, 2, 80)
    assert address_device(HOST, rlm)[1:] == ("Hall", "Bus Device 2.80")

    softm = {"type": ADDRESS_TYPE_SOFTM, "name": "Timer", "group": 10, "address": 1}
    assert address_device(HOST, softm)[2] == "Bus Device 10.1"

    aud = {"type": ADDRESS_TYPE_AUD, "group": 4, "address": 1}
    assert address_device(HOST, aud)[1:] == ("Audio 4.1", "BL-AUD 4.1")

    cover = {
        "type": ADDRESS_TYPE_SHUTTER,
        "name": "Front",
        "open_group": 3,
        "open_address": 1,
        "close_group": 3,
        "close_address": 2,
    }
    assert address_device(HOST, cover)[0] == get_cover_device_identifiers(
        HOST, 3, 1, 3, 2
    )

    room = {"type": ADDRESS_TYPE_SFEER, "name": "Living", "moods": [{}, {}]}
    assert address_device(HOST, room)[0] == get_sfeer_device_identifiers(
        HOST, "Living"
    )
    assert address_device(HOST, room)[2] == "Sfeer room (2 moods)"

    readonly = {"type": ADDRESS_TYPE_READONLY, "group": 1, "address": 5}
    assert address_device(HOST, readonly)[1] == "Read-only 1.5"

    rtc = {"type": ADDRESS_TYPE_RTC, "name": "Clock", "group": 1, "address": 9}
    assert address_device(HOST, rtc)[2] == "RTC 1.9"

    ldm = {"type": ADDRESS_TYPE_LDM, "name": "Lux", "group": 1, "address": 3}
    assert address_device(HOST, ldm)[2] == "LDM 1.3"

    tsm = {"type": ADDRESS_TYPE_TSM, "name": "Heat", "group": 1, "address": 4}
    assert address_device(HOST, tsm)[2] == "TSM 1.4"


def test_removed_address_is_no_longer_configured():
    current = [{"type": "rlm", "name": "Hall", "group": 2, "address": 80}]
    keep = configured_device_identifiers(HOST, current)
    gone = get_device_identifiers(HOST, 2, 11)
    assert device_no_longer_configured(gone, keep)
    assert not device_no_longer_configured(get_device_identifiers(HOST, 2, 80), keep)


def test_foreign_device_is_left_alone():
    keep = configured_device_identifiers(HOST, [])
    assert not device_no_longer_configured({("other", "x")}, keep)
    assert not device_no_longer_configured(set(), keep)


def test_device_kept_when_one_identifier_is_still_configured():
    keep = configured_device_identifiers(
        HOST, [{"type": "rlm", "group": 2, "address": 80}]
    )
    mixed = get_device_identifiers(HOST, 2, 80) | {(DOMAIN, f"{HOST}_2_11")}
    assert not device_no_longer_configured(mixed, keep)
