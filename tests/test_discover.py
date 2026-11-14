"""Gateway discovery replies (no Home Assistant, no network)."""

from __future__ import annotations

from b_logicx.discover import (
    DISCOVER_PORT,
    DISCOVER_QUERY,
    DISCOVER_WAIT_S,
    DiscoveredGateway,
    build_setup_record,
    firmware_mac,
    firmware_reply,
    firmware_version,
    gateway_step_id,
    ip_from_gateway_step,
    manifest_version,
    is_gateway_reply,
    local_ipv4_addresses,
    reply_to_discover,
    setup_hostname,
    version_octets,
)

# Setup record from the first captured module. The text at the end is its hostname.
_NWM_REPLY = bytes.fromhex(
    "000000f9"
    "000005000000002d0000000000000000"
    "4c0202001127000000000000c00000000000f700"
    "00000000000000000000000000000000000000000000000000000000"
    "4c0202001227000000000000c00000000000f700"
    "00000000000000000000000000000000000000000000000000000000"
    "622d6c6f67696378"
)

# Firmware reply from the same module. It is a different query and not a gateway row.
_FIRMWARE_REPLY = bytes.fromhex(
    "000000f70020a006465957124b16000062a7adb7ff00000000204af00921"
)

# Second captured module. Same channel, no hostname, version byte 70.
_UNNAMED_REPLY = _NWM_REPLY[:6] + b"\x00" + _NWM_REPLY[7:-8] + bytes(8)
_UNNAMED_FIRMWARE = bytes.fromhex(
    "000000f7002070064659e211dd15000062a78e21ff00000000204af02e56"
)


def test_query_matches_the_blconfig_broadcast():
    assert DISCOVER_PORT == 30718
    assert DISCOVER_QUERY == b"\x00\x00\x00\xf8"
    assert DISCOVER_WAIT_S == 1.0


def test_port_10001_channel_is_a_gateway_with_or_without_a_hostname():
    assert is_gateway_reply(_NWM_REPLY) is True
    assert is_gateway_reply(_UNNAMED_REPLY) is True
    assert setup_hostname(_NWM_REPLY) == "b-logicx"
    assert setup_hostname(_UNNAMED_REPLY) is None
    assert b"b-logicx" not in _UNNAMED_REPLY
    assert is_gateway_reply(build_setup_record(25000)) is False


def test_other_replies_are_not_a_gateway():
    assert is_gateway_reply(_FIRMWARE_REPLY) is False
    assert is_gateway_reply(b"\x00\x00\x00\xf9" + b"\x00" * 20) is False
    assert is_gateway_reply(b"") is False
    assert is_gateway_reply(b"\x00\x00\xf9") is False


def test_repeater_record_names_its_port_and_not_a_second_one():
    record = build_setup_record(10001)
    assert len(record) == 124
    assert is_gateway_reply(record) is True
    assert record[:68] == _NWM_REPLY[:68]
    assert record[24:26] == (10001).to_bytes(2, "little")
    assert record[68:116] == bytes(48)
    assert (10002).to_bytes(2, "little") not in record
    assert record.endswith(b"b-logicx")


def test_repeater_record_uses_the_open_port():
    record = build_setup_record(25000)
    assert record[24:26] == (25000).to_bytes(2, "little")
    assert (10001).to_bytes(2, "little") not in record
    assert (10002).to_bytes(2, "little") not in record


def _shown_version(version: str) -> str:
    payload = b"\x00\x00\x00\xf7\x00\x00" + version_octets(version)
    shown = firmware_version(payload)
    assert shown is not None
    return shown


def test_parentheses_follow_the_first_digits_of_the_manifest_version():
    assert version_octets("0.9.9.5") == bytes.fromhex("9000")
    assert _shown_version("0.9.9.5") == "0.9"
    assert _shown_version("1.4.2") == "1.4"
    assert _shown_version("0.10.1") == "0.1"
    assert _shown_version("12.3.0") == "1.3"
    mac = bytes.fromhex("020000000001")
    reply = firmware_reply(mac)
    assert reply is not None
    assert len(reply) == 30
    assert reply[:6] == _FIRMWARE_REPLY[:6]
    assert reply[6:8] == version_octets(manifest_version())
    assert reply[8:24] == _FIRMWARE_REPLY[8:24]
    assert reply.endswith(mac)
    assert firmware_version(reply) == _shown_version(manifest_version())
    assistio = firmware_reply(bytes.fromhex("a55157100000"))
    assert reply_to_discover(b"\x00\x00\x00\xf6", 10001) == assistio
    assert firmware_mac(assistio) == "A5-51-57-10-00-00"
    assert reply_to_discover(DISCOVER_QUERY, 10001) == build_setup_record(10001)
    assert reply_to_discover(b"", 10001) is None


def test_this_host_is_among_its_own_addresses():
    assert "127.0.0.1" in local_ipv4_addresses()


def test_firmware_identity_fills_the_discovery_row():
    assert firmware_version(_FIRMWARE_REPLY) == "6.A"
    assert firmware_mac(_FIRMWARE_REPLY) == "00-20-4A-F0-09-21"
    assert firmware_version(_UNNAMED_FIRMWARE) == "6.7"
    assert firmware_mac(_UNNAMED_FIRMWARE) == "00-20-4A-F0-2E-56"
    assert firmware_version(b"") is None
    assert firmware_mac(b"") is None
    assert (
        DiscoveredGateway(
            "192.0.2.10",
            mac=firmware_mac(_FIRMWARE_REPLY),
            hostname=setup_hostname(_NWM_REPLY),
            version=firmware_version(_FIRMWARE_REPLY),
        ).label
        == "192.0.2.10 · 00-20-4A-F0-09-21 · b-logicx · 6.A"
    )
    assert (
        DiscoveredGateway(
            "192.0.2.20",
            mac=firmware_mac(_UNNAMED_FIRMWARE),
            hostname=setup_hostname(_UNNAMED_REPLY),
            version=firmware_version(_UNNAMED_FIRMWARE),
        ).label
        == "192.0.2.20 · 00-20-4A-F0-2E-56 · 6.7"
    )
    assert DiscoveredGateway("192.0.2.20").label == "192.0.2.20"


def test_step_id_roundtrip_keeps_the_address():
    assert gateway_step_id("192.0.2.10") == "gw_192_0_2_10"
    assert ip_from_gateway_step("gw_192_0_2_10") == "192.0.2.10"
    assert ip_from_gateway_step("host") is None
    assert ip_from_gateway_step("gw_not_an_ip") is None
