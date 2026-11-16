"""ODS 12 member reader. Synthetic pages only, no real installation data."""

from __future__ import annotations

import struct

import pytest

from b_logicx.bhs_client import classify_members
from b_logicx.fdb_members import FdbError, read_members

PAGE = 8192

# RDB$RELATIONS field ids. The reader locates RDB$FIELD_ID by these values.
_CATALOG_FIELDS = {
    "RDB$VIEW_BLR": 0,
    "RDB$VIEW_SOURCE": 1,
    "RDB$DESCRIPTION": 2,
    "RDB$RELATION_ID": 3,
    "RDB$SYSTEM_FLAG": 4,
    "RDB$DBKEY_LENGTH": 5,
    "RDB$FORMAT": 6,
    "RDB$FIELD_ID": 7,
    "RDB$RELATION_NAME": 8,
}

# Descriptor index of each MEMBERS column in the synthetic format.
_MEMBER_FIELDS = (
    ("MEMBERID", 0),
    ("NAME", 1),
    ("GROUP", 2),
    ("ADDRESS", 3),
    ("VERSION", 4),
    ("MEMBERTYPE", 5),
)


def _rle(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        size = min(127, len(data) - index)
        out.append(size)
        out.extend(data[index : index + size])
        index += size
    return bytes(out)


def _record(payload: bytes, flags: int = 0, fmt: int = 0) -> bytes:
    header = bytearray(13)
    struct.pack_into("<H", header, 10, flags)
    header[12] = fmt
    return bytes(header) + _rle(payload)


def _pointer(relation: int, slots: list[int]) -> bytearray:
    page = bytearray(PAGE)
    page[0] = 4
    struct.pack_into("<H", page, 24, len(slots))
    struct.pack_into("<H", page, 26, relation)
    for index, number in enumerate(slots):
        struct.pack_into("<I", page, 32 + 4 * index, number)
    return page


def _data(relation: int, slots: list[bytes]) -> bytearray:
    page = bytearray(PAGE)
    page[0] = 5
    struct.pack_into("<H", page, 20, relation)
    struct.pack_into("<H", page, 22, len(slots))
    end = PAGE
    for index, raw in enumerate(slots):
        end -= len(raw)
        if end < 24 + 4 * (index + 1):
            raise RuntimeError("synthetic page is full")
        struct.pack_into("<HH", page, 24 + 4 * index, end, len(raw))
        page[end : end + len(raw)] = raw
    return page


def _pages_row(page_no: int, relation: int, page_type: int) -> bytes:
    raw = bytearray(18)
    struct.pack_into("<I", raw, 4, page_no)
    struct.pack_into("<H", raw, 8, relation)
    struct.pack_into("<H", raw, 16, page_type)
    return _record(bytes(raw))


def _relation_row(relation: int, name: str) -> bytes:
    raw = bytearray(80)
    struct.pack_into("<h", raw, 32, relation)
    encoded = name.encode("ascii")
    raw[42 : 42 + len(encoded)] = encoded
    return _record(bytes(raw))


def _field_row(field: str, relation: str, field_id: int) -> bytes:
    raw = bytearray(320)
    raw[4 : 4 + 31] = b" " * 31
    raw[35 : 35 + 31] = b" " * 31
    raw[4 : 4 + len(field)] = field.encode("ascii")
    raw[35 : 35 + len(relation)] = relation.encode("ascii")
    struct.pack_into("<h", raw, 290, field_id)
    return _record(bytes(raw))


def _member_row(
    group: int,
    address: int,
    name: str,
    version: str,
    member_type: int,
    member_id: str,
    flags: int = 0,
    incomplete_prefix: bool = False,
) -> bytes:
    raw = bytearray(104)

    def varying(offset: int, text: str) -> None:
        encoded = text.encode("ascii")
        struct.pack_into("<H", raw, offset, len(encoded))
        raw[offset + 2 : offset + 2 + len(encoded)] = encoded

    varying(4, member_id)
    varying(38, name)
    struct.pack_into("<i", raw, 72, group)
    struct.pack_into("<i", raw, 76, address)
    varying(80, version)
    struct.pack_into("<i", raw, 100, member_type)
    payload = bytes(raw)
    if incomplete_prefix:
        payload = b"\x00" * 13 + payload
    return _record(payload, flags=flags)


def _format_blob() -> bytes:
    fields = (
        (3, 32, 4),
        (3, 32, 38),
        (9, 4, 72),
        (9, 4, 76),
        (3, 16, 80),
        (9, 4, 100),
    )
    blob = bytearray(2 + 12 * len(fields))
    struct.pack_into("<H", blob, 0, len(fields))
    for number, (dtype, length, offset) in enumerate(fields):
        index = 2 + number * 12
        blob[index] = dtype
        struct.pack_into("<H", blob, index + 2, length)
        struct.pack_into("<I", blob, index + 8, offset)
    return bytes(blob)


def _blob_slot(segment: bytes) -> bytes:
    raw = bytearray(28 + 2 + len(segment))
    struct.pack_into("<H", raw, 10, 16)
    struct.pack_into("<I", raw, 16, 1)
    struct.pack_into("<I", raw, 20, len(segment))
    struct.pack_into("<H", raw, 28, len(segment))
    raw[30 : 30 + len(segment)] = segment
    return bytes(raw)


def _format_row() -> bytes:
    raw = bytearray(16)
    raw[0] = 0xF8
    struct.pack_into("<h", raw, 4, 128)
    struct.pack_into("<H", raw, 8, 8)
    struct.pack_into("<I", raw, 12, 1)
    return _record(bytes(raw))


def _header(ods: int = 0x800C, flags: int = 0x10, page_size: int = 8192) -> bytearray:
    page = bytearray(PAGE)
    page[0] = 1
    struct.pack_into("<H", page, 16, page_size)
    struct.pack_into("<H", page, 18, ods)
    struct.pack_into("<I", page, 20, 1)
    struct.pack_into("<H", page, 42, flags)
    return page


def _database() -> bytes:
    field_rows = [
        _field_row(name, "RDB$RELATIONS", field_id)
        for name, field_id in _CATALOG_FIELDS.items()
    ]
    field_rows.extend(
        _field_row(name, "MEMBERS", field_id) for name, field_id in _MEMBER_FIELDS
    )
    pages = [
        _header(),
        _pointer(0, [2]),
        _data(
            0,
            [
                _pages_row(3, 6, 4),
                _pages_row(4, 5, 4),
                _pages_row(5, 8, 4),
                _pages_row(6, 128, 4),
            ],
        ),
        _pointer(6, [7]),
        _pointer(5, [8]),
        _pointer(8, [9]),
        _pointer(128, [10]),
        _data(6, [_relation_row(6, "RDB$RELATIONS"), _relation_row(128, "MEMBERS")]),
        _data(5, field_rows),
        _data(8, [_format_row(), _blob_slot(_format_blob())]),
        _data(
            128,
            [
                _member_row(2, 1, "spots tv", "RLM_4", 1, "m-rlm"),
                _member_row(4, 10, "lamp", "DIM1K_1", 2, "m-dim"),
                _member_row(9, 9, "gone", "RLM_4", 1, "m-gone", flags=1),
                _member_row(8, 8, "old", "RLM_4", 1, "m-old", flags=2),
                _member_row(
                    7,
                    4,
                    "spare",
                    "SoftM",
                    4,
                    "m-soft",
                    flags=8,
                    incomplete_prefix=True,
                ),
                _member_row(
                    0,
                    0,
                    "",
                    "",
                    0,
                    "",
                    flags=8,
                    incomplete_prefix=True,
                ),
            ],
        ),
    ]
    return b"".join(pages)


def test_rejects_a_header_that_is_not_ods_12():
    with pytest.raises(FdbError):
        read_members(b"")
    with pytest.raises(FdbError):
        read_members(bytes(_header(ods=0x800B)))
    with pytest.raises(FdbError):
        read_members(bytes(_header(page_size=4096)))
    with pytest.raises(FdbError):
        read_members(bytes(_header(flags=0x40)))


def test_synthetic_members_reach_the_checklist():
    members = read_members(_database())
    assert len(members) == 3
    result = classify_members(members)
    assert sorted(item.key for item in result.candidates) == [
        "dimmer:4.10",
        "rlm:2.1",
        "softm:7.4",
    ]
    assert result.leftover == []
    by_key = {item.key: item for item in result.candidates}
    assert by_key["rlm:2.1"].entry["name"] == "spots tv"
    assert by_key["dimmer:4.10"].entry["type"] == "dimmer"
    spare = by_key["softm:7.4"]
    assert spare.entry["name"] == "spare"
    assert spare.label == "7.4 spare* — SoftM"
    assert "*" not in spare.entry["name"]
