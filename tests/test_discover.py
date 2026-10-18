"""Gateway discovery replies (no Home Assistant, no network)."""

from __future__ import annotations

from b_logicx.discover import (
    DISCOVER_PORT,
    DISCOVER_QUERY,
    DISCOVER_WAIT_S,
    gateway_step_id,
    ip_from_gateway_step,
    is_gateway_reply,
)

# Setup record answered by 192.168.50.150. The text at the end is b-logicx.
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


def test_query_matches_the_blconfig_broadcast():
    assert DISCOVER_PORT == 30718
    assert DISCOVER_QUERY == b"\x00\x00\x00\xf8"
    assert DISCOVER_WAIT_S == 1.0


def test_setup_record_containing_b_logicx_is_a_gateway():
    assert is_gateway_reply(_NWM_REPLY) is True
    assert is_gateway_reply(_NWM_REPLY.upper()) is True


def test_other_replies_are_not_a_gateway():
    assert is_gateway_reply(_FIRMWARE_REPLY) is False
    assert is_gateway_reply(b"\x00\x00\x00\xf9" + b"\x00" * 20) is False
    assert is_gateway_reply(b"") is False
    assert is_gateway_reply(b"\x00\x00\xf9") is False


def test_step_id_roundtrip_keeps_the_address():
    assert gateway_step_id("192.168.50.150") == "gw_192_168_50_150"
    assert ip_from_gateway_step("gw_192_168_50_150") == "192.168.50.150"
    assert ip_from_gateway_step("host") is None
    assert ip_from_gateway_step("gw_not_an_ip") is None
