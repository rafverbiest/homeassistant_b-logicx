"""BHS member classify and REST client (no Home Assistant, no live BHS)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from address_config import (
    dump_addresses_yaml,
    normalize_yaml_entry,
    parse_integration_settings,
    settings_for_export,
)
from b_logicx.bhs_client import (
    BHS_DEFAULT_PORT,
    BhsClient,
    BhsPendingError,
    BhsSecuredError,
    SecureSample,
    classify_members,
    encrypt_bhs_body,
    format_secure_dump,
    generate_device_credentials,
    leftover_line,
    normalize_host,
    read_member_list,
)
from const import CONF_BHS_DEVICE_ID, CONF_BHS_PRIVATE_KEY, CONF_BHS_PUBLIC_KEY


SPEC_MEMBERS = [
    {
        "memberID": "2001_spotstv_2.1",
        "address": 1,
        "group": 2,
        "name": "spots tv",
        "version": "RLM_4",
        "memberType": 1,
    },
    {
        "memberID": "2001_spotsbur_3.1",
        "address": 1,
        "group": 3,
        "name": "spots bureau",
        "version": "RLM_4",
        "memberType": 1,
    },
    {
        "memberID": "2001_thermowk_1.2",
        "address": 2,
        "group": 1,
        "name": "thermostaat woonkamer",
        "version": "TSM_52",
        "memberType": 7,
    },
]


def _by_kind(result):
    return {item.kind: item for item in result.candidates}


def test_default_port_is_rest_proxy():
    assert BHS_DEFAULT_PORT == 10014


def test_normalize_host_strips_scheme():
    assert normalize_host(" http://192.168.50.216/ ") == "192.168.50.216"
    assert normalize_host("https://bhs.local") == "bhs.local"


def test_spec_getmembers_example_maps_rlm_and_tsm():
    result = classify_members(SPEC_MEMBERS)
    kinds = sorted(item.kind for item in result.candidates)
    assert kinds == ["rlm", "rlm", "tsm"]
    assert result.leftover == []
    assert result.already == []
    labels = [item.label for item in result.candidates]
    assert "2.1 spots tv — RLM" in labels
    tsm = next(item for item in result.candidates if item.kind == "tsm")
    assert normalize_yaml_entry(tsm.entry)["type"] == "tsm"
    rlm = next(item for item in result.candidates if item.entry["address"] == 1 and item.entry["group"] == 2)
    saved = normalize_yaml_entry(rlm.entry)
    assert saved["on_command"] == "Set"
    assert saved["off_command"] == "Reset"


def test_type20_consecutive_rlm_becomes_one_cover():
    members = [
        {
            "memberID": "a",
            "group": 3,
            "address": 5,
            "name": "zonnescherm_OP",
            "version": "RLM_4",
            "memberType": 20,
        },
        {
            "memberID": "b",
            "group": 3,
            "address": 6,
            "name": "zonnescherm_NEER",
            "version": "RLM_4",
            "memberType": 20,
        },
    ]
    result = classify_members(members)
    assert len(result.candidates) == 1
    item = result.candidates[0]
    assert item.kind == "shutter"
    assert item.entry["open_address"] == 5
    assert item.entry["close_address"] == 6
    assert item.entry["name"] == "zonnescherm"
    saved = normalize_yaml_entry(item.entry)
    assert saved["type"] == "shutter"
    assert "rolluik" in classify_members(members, lang="nl").candidates[0].label


def test_unpaired_type20_is_leftover_not_rlm():
    members = [
        {
            "memberID": "a",
            "group": 3,
            "address": 5,
            "name": "half",
            "version": "RLM_4",
            "memberType": 20,
        }
    ]
    result = classify_members(members)
    assert result.candidates == []
    assert any("type 20" in line for line in result.leftover)


def test_type1_rlm_is_never_auto_paired():
    members = [
        {
            "memberID": "a",
            "group": 3,
            "address": 5,
            "name": "luik_OP",
            "version": "RLM_4",
            "memberType": 1,
        },
        {
            "memberID": "b",
            "group": 3,
            "address": 6,
            "name": "luik_NEER",
            "version": "RLM_4",
            "memberType": 1,
        },
    ]
    result = classify_members(members)
    assert [item.kind for item in result.candidates] == ["rlm", "rlm"]


def test_cover_without_name_suffix_uses_lower_address_as_open():
    members = [
        {
            "memberID": "b",
            "group": 3,
            "address": 8,
            "name": "down",
            "version": "rlm_4",
            "memberType": 20,
        },
        {
            "memberID": "a",
            "group": 3,
            "address": 7,
            "name": "up",
            "version": "RLM_4",
            "memberType": 20,
        },
    ]
    item = classify_members(members).candidates[0]
    assert item.entry["open_address"] == 7
    assert item.entry["close_address"] == 8


def test_softm_dimmer_sensors_drop_inm_and_exu():
    members = [
        {
            "memberID": "s",
            "group": 10,
            "address": 1,
            "name": "BWM_hall_bypass",
            "version": "SOFTM",
            "memberType": 4,
        },
        {
            "memberID": "d",
            "group": 5,
            "address": 14,
            "name": "DIM_keuken",
            "version": "DIM1K_15",
            "memberType": 2,
        },
        {
            "memberID": "i",
            "group": 1,
            "address": 8,
            "name": "PIR",
            "version": "INM_1",
            "memberType": 3,
        },
        {
            "memberID": "e",
            "group": 1,
            "address": 7,
            "name": "motion parking",
            "version": "EXU_192",
            "memberType": 17,
        },
        {
            "memberID": "l",
            "group": 1,
            "address": 9,
            "name": "Licht",
            "version": "LDM_93",
            "memberType": 11,
        },
        {
            "memberID": "w",
            "group": 1,
            "address": 11,
            "name": "Wind",
            "version": "WSM_112",
            "memberType": 13,
        },
        {
            "memberID": "c",
            "group": 1,
            "address": 13,
            "name": "klok",
            "version": "RTC_84",
            "memberType": 99,
        },
    ]
    result = classify_members(members)
    kinds = sorted(item.kind for item in result.candidates)
    assert kinds == ["dimmer", "ldm", "rtc", "softm", "wsm"]
    assert not any(
        item.entry.get("name") in {"PIR", "motion parking"}
        for item in result.candidates
    )
    assert not any("INM" in line or "EXU" in line for line in result.leftover)
    dimmer = next(
        item
        for item in classify_members(members).candidates
        if item.kind == "dimmer"
    )
    saved = normalize_yaml_entry(dimmer.entry)
    assert saved["remembers_level"] is False
    assert saved["participates_in_moods"] is True
    softm = next(
        item
        for item in classify_members(members).candidates
        if item.kind == "softm"
    )
    saved_softm = normalize_yaml_entry(softm.entry)
    assert saved_softm["enable_softm_status_tracking"] is True


def test_sfeer_groups_sdim_and_skips_stop_reset_record():
    members = [
        {
            "memberID": "m1",
            "group": 5,
            "address": 221,
            "name": "TV",
            "version": "SDIM",
            "memberType": 19,
        },
        {
            "memberID": "m2",
            "group": 5,
            "address": 222,
            "name": "eten",
            "version": "SDIM",
            "memberType": 19,
        },
        {
            "memberID": "stop",
            "group": 5,
            "address": 220,
            "name": "Stop Dim",
            "version": "SDIM",
            "memberType": 19,
        },
        {
            "memberID": "reset",
            "group": 5,
            "address": 229,
            "name": "GroepsReset Dim",
            "version": "SDIM",
            "memberType": 19,
        },
        {
            "memberID": "rec",
            "group": 5,
            "address": 230,
            "name": "Record sfeer",
            "version": "SDIM",
            "memberType": 19,
        },
    ]
    result = classify_members(members)
    assert len(result.candidates) == 1
    item = result.candidates[0]
    assert item.kind == "sfeer"
    assert item.entry["name"] == "Sfeer 5"
    assert [m["address"] for m in item.entry["moods"]] == [221, 222]
    saved = normalize_yaml_entry(item.entry)
    assert saved["type"] == "sfeer"
    assert len(saved["moods"]) == 2
    leftover_text = " ".join(result.leftover).casefold()
    assert "stop dim" in leftover_text
    assert "groepsreset" in leftover_text
    assert "record" in leftover_text


def test_already_configured_cover_and_rlm_are_listed_not_checked():
    members = SPEC_MEMBERS + [
        {
            "memberID": "c1",
            "group": 3,
            "address": 5,
            "name": "luik_OP",
            "version": "RLM_4",
            "memberType": 20,
        },
        {
            "memberID": "c2",
            "group": 3,
            "address": 6,
            "name": "luik_NEER",
            "version": "RLM_4",
            "memberType": 20,
        },
    ]
    occupied = {(2, 1), (3, 5)}
    result = classify_members(members, occupied)
    keys = {item.key for item in result.candidates}
    assert "rlm:2.1" not in keys
    assert not any(item.kind == "shutter" for item in result.candidates)
    assert any("2.1" in line for line in result.already)
    assert any("3.5" in line for line in result.already)
    assert any(item.key == "rlm:3.1" for item in result.candidates)


def test_unknown_types_go_to_leftover():
    members = [
        {
            "memberID": "k",
            "group": 1,
            "address": 1,
            "name": "Klavier",
            "version": "KLA_42",
            "memberType": 6,
        }
    ]
    result = classify_members(members)
    assert result.candidates == []
    assert leftover_line(1, 1, "Klavier", "KLA_42", 6) in result.leftover


def test_rows_without_memberid_skipped_when_others_have_one():
    members = [
        {
            "memberID": "a",
            "group": 2,
            "address": 1,
            "name": "ok",
            "version": "RLM_4",
            "memberType": 1,
        },
        {
            "memberID": "",
            "group": 2,
            "address": 2,
            "name": "gap",
            "version": "RLM_4",
            "memberType": 1,
        },
    ]
    result = classify_members(members)
    assert [item.entry["address"] for item in result.candidates] == [1]
    assert any("gap" in line for line in result.leftover)


def test_old_bhs_without_memberid_still_imports():
    members = [
        {
            "group": 2,
            "address": 1,
            "name": "spots",
            "version": "RLM_4",
            "memberType": 1,
        }
    ]
    result = classify_members(members)
    assert len(result.candidates) == 1


# Thank you to jeroendw88 (https://github.com/jeroendw88/bhs-homeassistant) for providing member types and example JSON data!
# API: https://b-logicx.be/Software/BHS/API_Docs/index.html
def test_redacted_member_dump_ignores_count_and_inm():
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "bhs_members.json").read_text()
    )
    assert raw["count"] == 164
    result = classify_members(raw["members"])
    assert len(raw["members"]) == 28
    kinds = sorted(item.kind for item in result.candidates)
    assert "readonly" not in kinds
    assert kinds.count("rlm") == 2
    assert kinds.count("shutter") == 2
    assert kinds.count("dimmer") == 2
    assert kinds.count("softm") == 2
    assert "sfeer" in kinds
    assert "rtc" in kinds
    names = {item.entry.get("name") for item in result.candidates}
    assert "hall contact 1" not in names
    assert "hall contact 2" not in names
    assert "motion parking" not in names
    assert "motion terrace" not in names
    assert not any(
        "INM" in line or "EXU" in line or "hall contact" in line
        for line in result.leftover
    )
    sfeer = next(item for item in result.candidates if item.kind == "sfeer")
    assert len(sfeer.entry["moods"]) == 8
    assert all(normalize_yaml_entry(item.entry) for item in result.candidates)


def test_yaml_export_keeps_stored_bhs_keys():
    private = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    public = "-----BEGIN PUBLIC KEY-----\npub\n-----END PUBLIC KEY-----"
    device = "550e8400-e29b-41d4-a716-446655440000"
    exported = settings_for_export(
        {
            CONF_BHS_DEVICE_ID: device,
            CONF_BHS_PRIVATE_KEY: private,
            CONF_BHS_PUBLIC_KEY: public,
        }
    )
    assert exported[CONF_BHS_DEVICE_ID] == device
    assert exported[CONF_BHS_PRIVATE_KEY] == private
    assert exported[CONF_BHS_PUBLIC_KEY] == public
    dumped = dump_addresses_yaml([], options=exported)
    parsed, err = parse_integration_settings(dumped)
    assert err is None
    assert parsed[CONF_BHS_DEVICE_ID] == device
    assert parsed[CONF_BHS_PRIVATE_KEY] == private
    assert parsed[CONF_BHS_PUBLIC_KEY] == public
    without, err = parse_integration_settings("addresses: []\n")
    assert err is None
    assert without is None


class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload
        self.headers = {"Content-Type": "application/json"}

    async def json(self, content_type=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload

    async def text(self):
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []
        self.sent_headers: list[dict] = []

    def request(self, method, url, headers=None, json=None, data=None, timeout=None):
        path = url.split("/api", 1)[-1]
        self.calls.append((method, path, data if data is not None else json))
        self.sent_headers.append(dict(headers or {}))
        status, payload = self.routes[(method, path)]
        return _FakeResponse(status, payload)


def test_get_members_posts_empty_object():
    session = _FakeSession(
        {("POST", "/members/getMembers"): (200, {"count": 0, "members": []})}
    )
    client = BhsClient(session, "192.168.50.216", 10014, "550e8400-e29b-41d4-a716-446655440000")

    async def _run():
        return await client.get_members()

    assert asyncio.run(_run()) == []
    assert session.calls == [("POST", "/members/getMembers", {})]


def test_register_pending_and_secured_and_encrypted_blob():
    session = _FakeSession(
        {
            ("POST", "/device/register"): (
                201,
                {"registered": True, "status": "Pending"},
            ),
            ("GET", "/bhs/isSecured"): (200, {"isSecure": True}),
            ("POST", "/members/getMembers"): (
                200,
                {"response": "AESencryptedstring=="},
            ),
        }
    )
    client = BhsClient(session, "bhs.local", 10014, "550e8400-e29b-41d4-a716-446655440000")

    async def _run():
        assert await client.register("-----BEGIN PUBLIC KEY-----\nX\n") == "Pending"
        assert await client.is_secured() is True
        with pytest.raises(BhsSecuredError):
            await client.get_members()

    asyncio.run(_run())


def test_pending_approval_on_later_call():
    session = _FakeSession(
        {("GET", "/bhs/isSecured"): (403, {"error": "pending approval"})}
    )
    client = BhsClient(session, "bhs.local", 10014, "550e8400-e29b-41d4-a716-446655440000")

    async def _run():
        with pytest.raises(BhsPendingError):
            await client.is_secured()

    asyncio.run(_run())


def _decrypt_bhs_body(blob: str, private_pem: str) -> bytes:
    import base64

    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    part1, part2 = blob.split("\r\n---\r\n", 1)
    private_key = serialization.load_pem_private_key(
        private_pem.encode("ascii"), password=None
    )
    line = private_key.decrypt(
        base64.b64decode(part1), asym_padding.PKCS1v15()
    ).decode("ascii")
    key_b64, iv_b64 = line.split("|", 1)
    decryptor = Cipher(
        algorithms.AES(base64.b64decode(key_b64)),
        modes.CBC(base64.b64decode(iv_b64)),
    ).decryptor()
    padded = decryptor.update(base64.b64decode(part2)) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def test_encrypt_bhs_body_roundtrip():
    _device, private_pem, public_pem = generate_device_credentials()
    blob = encrypt_bhs_body("{}", public_pem)
    assert _decrypt_bhs_body(blob, private_pem) == b"{}"


def test_cleartext_members_are_classified_without_a_dump(tmp_path):
    member = {
        "memberID": "a",
        "group": 2,
        "address": 1,
        "name": "spots",
        "version": "RLM_4",
        "memberType": 1,
    }
    session = _FakeSession(
        {
            ("GET", "/bhs/isSecured"): (200, {"isSecure": False}),
            ("POST", "/members/getMembers"): (200, {"members": [member]}),
        }
    )
    client = BhsClient(session, "192.168.50.10", 10014, "device")
    dump_path = tmp_path / "b_logicx_bhs_secure.txt"

    async def _run():
        return await read_member_list(client)

    loaded = asyncio.run(_run())
    assert isinstance(loaded, list)
    assert not dump_path.exists()
    result = classify_members(loaded)
    assert [item.kind for item in result.candidates] == ["rlm"]
    assert ("POST", "/members/getMembers", {}) in session.calls


def test_secured_read_writes_a_sample_and_skips_classify(tmp_path):
    device = "550e8400-e29b-41d4-a716-446655440000"
    _device, private_pem, public_pem = generate_device_credentials()
    raw = '{"response": "abc\r\n---\r\ndef"}'
    session = _FakeSession(
        {
            ("GET", "/bhs/isSecured"): (200, {"isSecure": True}),
            ("GET", "/bhs/getPublicKey"): (200, {"publicKey": public_pem}),
            ("POST", "/members/getMembers"): (200, raw),
        }
    )
    client = BhsClient(session, "192.168.50.10", 10014, device)
    dump_path = tmp_path / "b_logicx_bhs_secure.txt"

    async def _run():
        loaded = await read_member_list(client)
        assert isinstance(loaded, SecureSample)
        dump_path.write_text(
            format_secure_dump(
                host="192.168.50.10",
                port=10014,
                device_id=device,
                private_pem=private_pem,
                sample=loaded,
            ),
            encoding="utf-8",
            newline="",
        )
        return loaded

    loaded = asyncio.run(_run())
    assert not isinstance(loaded, list)
    text = dump_path.read_bytes().decode("utf-8")
    assert private_pem.strip() in text
    assert device in text
    assert raw in text
    assert "response status: 200" in text
    assert _decrypt_bhs_body(loaded.request_body, private_pem) == b"{}"
    post_headers = session.sent_headers[-1]
    assert post_headers["Content-Type"] == "application/json"
    assert post_headers["x-device-id"] == device


def test_secured_refusal_is_saved_instead_of_raised():
    _device, _private_pem, public_pem = generate_device_credentials()
    session = _FakeSession(
        {
            ("GET", "/bhs/isSecured"): (200, {"isSecure": True}),
            ("GET", "/bhs/getPublicKey"): (200, {"publicKey": public_pem}),
            ("POST", "/members/getMembers"): (
                400,
                '{"error": "encryption failed"}',
            ),
        }
    )
    client = BhsClient(session, "bhs.local", 10014, "device")

    async def _run():
        return await read_member_list(client)

    loaded = asyncio.run(_run())
    assert isinstance(loaded, SecureSample)
    assert loaded.status == 400
    assert "encryption failed" in loaded.response_text
