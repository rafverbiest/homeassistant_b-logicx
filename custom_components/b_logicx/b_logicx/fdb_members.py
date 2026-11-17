"""Read bus members from a BLConfig Firebird database file.

The file is ODS 12 with 8192-byte pages, the database BLConfig stores
on disk. Only the MEMBERS relation is returned, and only the columns the
checklist already understands: group, address, name, version, memberType,
and memberID. Other tables are ignored.

A record Firebird marks incomplete still holds a member. Those rows are
returned too, with ``incomplete`` set. The checklist uses that only to
mark the name. It is not part of the stored entity.
"""

from __future__ import annotations

import struct
from typing import Any

PAGE_SIZE = 8192
_ODS_MAJOR = 12
_FIREBIRD_FLAG = 0x8000
_HDR_ENCRYPTED = 0x40

_PAG = 16
_RHD = 13
_RHDE = 15
_RHDF = 21
_DPG_RPT = 24
_PPG_PAGE = 32
_BLH = 28
_BLP = 28

_DELETED = 1
_CHAIN = 2
_FRAGMENT = 4
_INCOMPLETE = 8
_BLOB = 16
_STREAM = 32
_DAMAGED = 128
_LONG_TRAN = 1024

# Deleted, old, and damaged versions stay out. An incomplete record is kept:
# BLConfig still shows it, and the member image is in the record.
_DROP = _DELETED | _CHAIN | _DAMAGED | _BLOB
# Incomplete payload: padding, then the back-version page and line.
_INCOMPLETE_PREFIX = 13

# Pointer-page slots and data-page lines in a record number, for 8192-byte pages.
_DP_PER_PP = (PAGE_SIZE - _PPG_PAGE) // 5
_MAX_RECS = (PAGE_SIZE - _DPG_RPT) // (4 + _RHD)

_REL_PAGES = 0
_REL_RELATION_FIELDS = 5
_REL_RELATIONS = 6
_REL_FORMATS = 8

_DTYPE_TEXT = 1
_DTYPE_VARYING = 3
_DTYPE_SHORT = 8
_DTYPE_LONG = 9

# Field indexes of RDB$RELATIONS. These ids are part of ODS and stay put
# when a column is added at the end.
_RELATIONS_FIELD_IDS = {
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

# MEMBERS column to the getMembers key. NAAM is accepted when NAME is absent.
_MEMBER_COLUMNS = {
    "GROUP": "group",
    "ADDRESS": "address",
    "NAAM": "name",
    "NAME": "name",
    "VERSION": "version",
    "MEMBERTYPE": "memberType",
    "MEMBERID": "memberID",
}

_IDENT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")


class FdbError(Exception):
    """The file is not a readable ODS 12 database, or it has no members."""


def read_members(data: bytes) -> list[dict[str, Any]]:
    """Return getMembers-shaped dicts from an uploaded .fdb file."""
    db = _Database(data)
    relations = db.rows(_REL_RELATIONS)
    members_id = _members_relation(relations)
    columns = _member_field_ids(db.rows(_REL_RELATION_FIELDS))
    formats = db.formats(members_id)
    found: list[dict[str, Any]] = []
    for fmt, plain, incomplete in db.rows(members_id, keep_incomplete=True):
        desc = formats.get(fmt)
        if desc is None:
            continue
        values: dict[str, Any] = {}
        for key, fid in columns.items():
            if fid >= len(desc) or _is_null(plain, fid):
                values[key] = None
                continue
            values[key] = _decode_field(plain, desc[fid])
        group = values.get("group")
        address = values.get("address")
        if not isinstance(group, int) or not isinstance(address, int):
            continue
        member_type = values.get("memberType")
        name = values.get("name") or ""
        # A blank incomplete slot is not a member. BLConfig does not list it.
        if incomplete and not str(name).strip() and not (
            isinstance(member_type, int) and member_type
        ):
            continue
        item = {
            "group": group,
            "address": address,
            "name": name,
            "version": values.get("version") or "",
            "memberType": member_type if isinstance(member_type, int) else None,
            "memberID": values.get("memberID") or "",
        }
        if incomplete:
            item["incomplete"] = True
        found.append(item)
    if not found:
        raise FdbError("members not found")
    return found


def _align(offset: int, alignment: int) -> int:
    return (offset + alignment - 1) & ~(alignment - 1)


def _relations_offsets() -> tuple[int, int, int]:
    """Byte offsets of relation id, format, and name in RDB$RELATIONS.

    The null bitmap is rounded up to 4 bytes. A blob id is aligned to 8.
    The name is field 8, so its offset does not depend on how wide the
    name column is.
    """
    offset = 4
    saved: list[int] = []
    for align, size in (
        (8, 8),
        (8, 8),
        (8, 8),
        (2, 2),
        (2, 2),
        (2, 2),
        (2, 2),
        (2, 2),
        (1, 0),
    ):
        offset = _align(offset, align)
        saved.append(offset)
        offset += size
    return saved[3], saved[6], saved[8]


def _u16(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<H", buf, offset)[0]


def _u32(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<I", buf, offset)[0]


def _is_null(plain: bytes, field_id: int) -> bool:
    byte = field_id // 8
    if byte >= len(plain):
        return True
    return bool(plain[byte] & (1 << (field_id % 8)))


def _identifier(buf: bytes, offset: int) -> str:
    chars: list[str] = []
    i = offset
    while i < len(buf) and len(chars) < 64:
        char = chr(buf[i])
        if char not in _IDENT:
            break
        chars.append(char)
        i += 1
    if not chars or i >= len(buf) or buf[i] not in (0, 32):
        return ""
    return "".join(chars)


def _char_field(buf: bytes, offset: int, width: int) -> str:
    if offset < 0 or offset + width > len(buf):
        return ""
    raw = buf[offset : offset + width].split(b"\x00", 1)[0].rstrip(b" ")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return ""
    if not text or any(char not in _IDENT for char in text):
        return ""
    return text


def _decode_text(raw: bytes) -> str:
    cleaned = raw.split(b"\x00", 1)[0].rstrip(b" ")
    for encoding in ("utf-8", "cp1252"):
        try:
            return cleaned.decode(encoding)
        except UnicodeDecodeError:
            continue
    return cleaned.decode("latin-1")


def _decode_field(plain: bytes, desc: tuple[int, int, int, int]) -> Any:
    dtype, length, _flags, offset = desc
    if offset < 0 or offset >= len(plain):
        return None
    if dtype == _DTYPE_VARYING and offset + 2 <= len(plain):
        size = min(_u16(plain, offset), length)
        end = offset + 2 + size
        if end > len(plain):
            return None
        return _decode_text(plain[offset + 2 : end])
    if dtype == _DTYPE_TEXT:
        end = min(len(plain), offset + length)
        return _decode_text(plain[offset:end])
    if dtype == _DTYPE_SHORT and offset + 2 <= len(plain):
        return struct.unpack_from("<h", plain, offset)[0]
    if dtype == _DTYPE_LONG and offset + 4 <= len(plain):
        return struct.unpack_from("<i", plain, offset)[0]
    return None


def _members_relation(rows: list[tuple[int, bytes]]) -> int:
    rel_at, _fmt_at, name_at = _relations_offsets()
    found: int | None = None
    saw_catalog = False
    for _fmt, plain in rows:
        if len(plain) < name_at + 1:
            continue
        rel_id = struct.unpack_from("<h", plain, rel_at)[0]
        name = _identifier(plain, name_at)
        if rel_id == _REL_RELATIONS and name == "RDB$RELATIONS":
            saw_catalog = True
        if name == "MEMBERS" and found is None:
            found = rel_id
    if not saw_catalog or found is None:
        raise FdbError("members not found")
    return found


def _name_width(rows: list[tuple[int, bytes]]) -> int:
    for _fmt, plain in rows:
        if _identifier(plain, 4) != "RDB$RELATION_NAME":
            continue
        marker = b"RDB$RELATIONS"
        start = 5
        while True:
            index = plain.find(marker, start)
            if index < 0:
                break
            after = index + len(marker)
            if after < len(plain) and plain[after] in (0, 32):
                width = index - 4
                if 16 <= width <= 252:
                    return width
            start = index + 1
    raise FdbError("catalog unreadable")


def _field_id_offset(rows: list[tuple[int, bytes]], width: int) -> int:
    found: set[int] | None = None
    for _fmt, plain in rows:
        field = _char_field(plain, 4, width)
        relation = _char_field(plain, 4 + width, width)
        if relation != "RDB$RELATIONS" or field not in _RELATIONS_FIELD_IDS:
            continue
        expected = _RELATIONS_FIELD_IDS[field]
        hits = {
            offset
            for offset in range(0, len(plain) - 1, 2)
            if struct.unpack_from("<h", plain, offset)[0] == expected
        }
        found = hits if found is None else found & hits
    if not found:
        raise FdbError("catalog unreadable")
    return min(found)


def _member_field_ids(rows: list[tuple[int, bytes]]) -> dict[str, int]:
    width = _name_width(rows)
    fid_at = _field_id_offset(rows, width)
    columns: dict[str, int] = {}
    for _fmt, plain in rows:
        if len(plain) < fid_at + 2:
            continue
        field = _char_field(plain, 4, width)
        relation = _char_field(plain, 4 + width, width)
        if relation != "MEMBERS":
            continue
        key = _MEMBER_COLUMNS.get(field)
        if key is None:
            continue
        # NAME wins when the table also has a NAAM column.
        if key in columns and field != "NAME":
            continue
        columns[key] = struct.unpack_from("<h", plain, fid_at)[0]
    if "group" not in columns or "address" not in columns:
        raise FdbError("members not found")
    return columns


def _unpack(data: bytes, limit: int = 65536) -> bytes:
    """Undo the signed run-length encoding stored on a data page."""
    out = bytearray()
    index = 0
    size = len(data)
    while index < size:
        length = data[index]
        index += 1
        if length >= 128:
            length -= 256
        if length < 0:
            if index >= size:
                raise FdbError("bad record")
            out.extend(bytes((data[index],)) * (-length))
            index += 1
        elif length > 0:
            end = index + length
            if end > size:
                raise FdbError("bad record")
            out.extend(data[index:end])
            index = end
        if len(out) > limit:
            raise FdbError("bad record")
    return bytes(out)


def _descriptors(blob: bytes) -> list[tuple[int, int, int, int]]:
    if len(blob) < 2:
        raise FdbError("catalog unreadable")
    count = _u16(blob, 0)
    need = 2 + count * 12
    if count < 1 or len(blob) < need:
        raise FdbError("catalog unreadable")
    out = []
    for number in range(count):
        index = 2 + number * 12
        out.append(
            (
                blob[index],
                _u16(blob, index + 2),
                _u16(blob, index + 6),
                _u32(blob, index + 8),
            )
        )
    return out


def _segments(buf: bytes, total: int) -> bytes:
    out = bytearray()
    index = 0
    while len(out) < total and index + 2 <= len(buf):
        size = _u16(buf, index)
        index += 2
        if size == 0:
            continue
        end = index + size
        if end > len(buf):
            raise FdbError("catalog unreadable")
        out.extend(buf[index:end])
        index = end
    if len(out) < total:
        raise FdbError("catalog unreadable")
    return bytes(out[:total])


class _Database:
    def __init__(self, data: bytes) -> None:
        if len(data) < PAGE_SIZE or len(data) % PAGE_SIZE:
            raise FdbError("unsupported database")
        self.data = data
        self.pages = len(data) // PAGE_SIZE
        self._check_header()
        self.pointers = self._pointer_pages()

    def page(self, number: int) -> bytes:
        if number <= 0 or number >= self.pages:
            raise FdbError("catalog unreadable")
        start = number * PAGE_SIZE
        return self.data[start : start + PAGE_SIZE]

    def _check_header(self) -> None:
        page = self.data[:PAGE_SIZE]
        if page[0] != 1:
            raise FdbError("unsupported database")
        if _u16(page, 16) != PAGE_SIZE:
            raise FdbError("unsupported database")
        ods = _u16(page, 18)
        if (ods & 0x7FFF) != _ODS_MAJOR or not (ods & _FIREBIRD_FLAG):
            raise FdbError("unsupported database")
        # sequence is at 40, flags at 42. Bit 0x40 means the file is encrypted.
        if _u16(page, 42) & _HDR_ENCRYPTED:
            raise FdbError("unsupported database")
        self._pages_root = _u32(page, 20)

    def _pointer_pages(self) -> dict[int, dict[int, int]]:
        """Relation id to {pointer sequence: page number} from RDB$PAGES."""
        found: dict[int, dict[int, int]] = {}
        for _fmt, plain in self._rows_from_root(self._pages_root):
            if len(plain) < 18:
                continue
            page_no = _u32(plain, 4)
            rel_id = _u16(plain, 8)
            sequence = _u32(plain, 12)
            page_type = _u16(plain, 16)
            if page_type != 4 or page_no == 0:
                continue
            found.setdefault(rel_id, {})[sequence] = page_no
        if _REL_RELATIONS not in found or _REL_FORMATS not in found:
            raise FdbError("catalog unreadable")
        return found

    def rows(
        self, relation_id: int, *, keep_incomplete: bool = False
    ) -> list[tuple]:
        pointers = self.pointers.get(relation_id)
        if not pointers:
            raise FdbError("members not found")
        return self._rows_under(pointers, keep_incomplete=keep_incomplete)

    def _rows_under(
        self, pointers: dict[int, int], *, keep_incomplete: bool = False
    ) -> list[tuple]:
        data_pages = self._data_pages(pointers)
        tails = _fragment_tails(self, data_pages)
        out: list[tuple] = []
        for page_no in data_pages:
            out.extend(
                self._data_rows(page_no, tails, keep_incomplete=keep_incomplete)
            )
        return out

    def _data_pages(self, pointers: dict[int, int]) -> list[int]:
        found: list[int] = []
        seen_ptr: set[int] = set()
        seen_data: set[int] = set()
        for sequence in sorted(pointers):
            page_no = pointers[sequence]
            while page_no and page_no not in seen_ptr:
                seen_ptr.add(page_no)
                page = self.page(page_no)
                if page[0] != 4:
                    break
                _rel, _seq, nxt, slots = _pointer_slots(page)
                for data_page in slots:
                    if data_page and data_page not in seen_data:
                        seen_data.add(data_page)
                        found.append(data_page)
                page_no = nxt
        return found

    def formats(self, relation_id: int) -> dict[int, list[tuple[int, int, int, int]]]:
        out: dict[int, list[tuple[int, int, int, int]]] = {}
        for _fmt, plain in self.rows(_REL_FORMATS):
            if len(plain) < 16:
                continue
            rel_id = struct.unpack_from("<h", plain, 4)[0]
            format_no = struct.unpack_from("<h", plain, 6)[0]
            if rel_id != relation_id:
                continue
            try:
                blob = self._blob(plain[8:16])
                out[format_no] = _descriptors(blob)
            except FdbError:
                continue
        if not out:
            raise FdbError("members not found")
        return out

    def _rows_from_root(self, pointer_page: int) -> list[tuple[int, bytes]]:
        out = self._rows_under({0: pointer_page})
        if not out:
            raise FdbError("catalog unreadable")
        return out

    def _data_rows(
        self,
        page_no: int,
        tails: set[tuple[int, int]],
        *,
        keep_incomplete: bool = False,
    ) -> list[tuple]:
        try:
            page = self.page(page_no)
        except FdbError:
            return []
        if page[0] != 5:
            return []
        count = _u16(page, 22)
        out: list[tuple] = []
        for slot in range(count):
            if (page_no, slot) in tails:
                continue
            raw = _slot(page, slot)
            if raw is None or len(raw) < _RHD:
                continue
            flags = _u16(raw, 10)
            incomplete = bool(flags & _INCOMPLETE)
            if flags & _DROP or (incomplete and not keep_incomplete):
                continue
            try:
                compressed = self._fragment_bytes(page_no, slot, raw)
                plain = _unpack(compressed)
            except FdbError:
                continue
            if incomplete:
                if len(plain) <= _INCOMPLETE_PREFIX:
                    continue
                plain = plain[_INCOMPLETE_PREFIX:]
            if keep_incomplete:
                out.append((raw[12], plain, incomplete))
            else:
                out.append((raw[12], plain))
        return out

    def _fragment_bytes(self, page_no: int, slot: int, raw: bytes) -> bytes:
        parts: list[bytes] = []
        seen: set[tuple[int, int]] = set()
        current_page = page_no
        current_slot = slot
        current = raw
        for _ in range(32):
            if (current_page, current_slot) in seen:
                raise FdbError("bad record")
            seen.add((current_page, current_slot))
            flags = _u16(current, 10)
            if flags & _FRAGMENT:
                if len(current) < _RHDF:
                    raise FdbError("bad record")
                parts.append(current[_RHDF:])
                current_page = _u32(current, 15)
                current_slot = _u16(current, 19)
                nxt = self.page(current_page)
                if nxt[0] != 5:
                    raise FdbError("bad record")
                current = _slot(nxt, current_slot)
                if current is None:
                    raise FdbError("bad record")
                continue
            if flags & _LONG_TRAN:
                parts.append(current[_RHDE:])
            else:
                parts.append(current[_RHD:])
            return b"".join(parts)
        raise FdbError("bad record")

    def _blob(self, bid: bytes) -> bytes:
        if len(bid) < 8:
            raise FdbError("catalog unreadable")
        relation_id = _u16(bid, 0)
        number = _u32(bid, 4) + (bid[3] << 32)
        pointers = self.pointers.get(relation_id)
        if not pointers:
            raise FdbError("catalog unreadable")
        line = number % _MAX_RECS
        sequence = number // _MAX_RECS
        slot = sequence % _DP_PER_PP
        pp_sequence = sequence // _DP_PER_PP
        pointer_page = pointers.get(pp_sequence)
        if pointer_page is None:
            raise FdbError("catalog unreadable")
        page = self.page(pointer_page)
        if page[0] != 4:
            raise FdbError("catalog unreadable")
        _rel, _seq, _nxt, slots = _pointer_slots(page)
        if slot >= len(slots) or slots[slot] == 0:
            raise FdbError("catalog unreadable")
        data_page = self.page(slots[slot])
        if data_page[0] != 5:
            raise FdbError("catalog unreadable")
        raw = _slot(data_page, line)
        if raw is None or len(raw) < _BLH or not (_u16(raw, 10) & _BLOB):
            raise FdbError("catalog unreadable")
        level = raw[12]
        total = _u32(raw, 20)
        if level == 0:
            payload = raw[_BLH:]
            if _u16(raw, 10) & _STREAM:
                if len(payload) < total:
                    raise FdbError("catalog unreadable")
                return payload[:total]
            return _segments(payload, total)
        if level != 1:
            raise FdbError("catalog unreadable")
        page_count = _u32(raw, 4) + 1
        if _BLH + page_count * 4 > len(raw):
            raise FdbError("catalog unreadable")
        chunks = bytearray()
        for index in range(page_count):
            blob_page = self.page(_u32(raw, _BLH + 4 * index))
            if blob_page[0] != 8:
                raise FdbError("catalog unreadable")
            length = _u16(blob_page, 24)
            chunks.extend(blob_page[_BLP : _BLP + length])
        return _segments(bytes(chunks), total)


def _pointer_slots(page: bytes) -> tuple[int, int, int, list[int]]:
    sequence = _u32(page, 16)
    nxt = _u32(page, 20)
    count = _u16(page, 24)
    relation = _u16(page, 26)
    if count > (PAGE_SIZE - _PPG_PAGE) // 4:
        raise FdbError("catalog unreadable")
    slots = [_u32(page, _PPG_PAGE + 4 * index) for index in range(count)]
    return relation, sequence, nxt, slots


def _slot(page: bytes, index: int) -> bytes | None:
    count = _u16(page, 22)
    if index >= count:
        return None
    offset = _u16(page, _DPG_RPT + 4 * index)
    length = _u16(page, _DPG_RPT + 4 * index + 2)
    if offset == 0 or length == 0 or offset + length > PAGE_SIZE:
        return None
    return page[offset : offset + length]


def _fragment_tails(db: _Database, data_pages: list[int]) -> set[tuple[int, int]]:
    """Continuation slots of a fragmented record. They are not rows of their own."""
    tails: set[tuple[int, int]] = set()
    for page_no in data_pages:
        try:
            page = db.page(page_no)
        except FdbError:
            continue
        if page[0] != 5:
            continue
        count = _u16(page, 22)
        for slot in range(count):
            raw = _slot(page, slot)
            if raw is None or len(raw) < _RHDF or not (_u16(raw, 10) & _FRAGMENT):
                continue
            nxt_page = _u32(raw, 15)
            nxt_slot = _u16(raw, 19)
            seen = {(page_no, slot)}
            for _ in range(32):
                tails.add((nxt_page, nxt_slot))
                if (nxt_page, nxt_slot) in seen:
                    break
                seen.add((nxt_page, nxt_slot))
                try:
                    host = db.page(nxt_page)
                except FdbError:
                    break
                if host[0] != 5:
                    break
                nxt = _slot(host, nxt_slot)
                if nxt is None or len(nxt) < _RHDF or not (_u16(nxt, 10) & _FRAGMENT):
                    break
                nxt_page = _u32(nxt, 15)
                nxt_slot = _u16(nxt, 19)
    return tails
