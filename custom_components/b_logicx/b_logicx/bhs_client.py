"""One-shot BHS REST client: register, read members, classify.

Key material follows the BHS REST API “Koppelen” procedure
(https://b-logicx.be/Software/BHS/API_Docs/index.html):

1. Make a UUID v4. That value is ``x-device-id`` on every call.
2. Make an RSA-2048 key pair (public exponent 65537). The private key
   never goes on the wire. The public key is SubjectPublicKeyInfo PEM
   (``BEGIN PUBLIC KEY``), the form Chilkat ``LoadFromString`` accepts.
3. ``POST /api/device/register`` with that UUID, a name, a platform, and
   the public PEM. The body is always plain JSON, including when the BHS
   later has ``ISSECURE`` on — the server does not have our key yet.
4. ``GET /api/bhs/isSecured``. ``false``: ``POST /api/members/getMembers``
   with plain ``{}``. ``true``: ``GET /api/bhs/getPublicKey``, then POST
   ``{}`` as the documented hybrid blob and keep the raw reply. The
   options flow writes that exchange to a file and does not import.

Pending approval is a separate gate from ``ISSECURE``. Register itself
is never encrypted and does not need an approved device. A new device on
a BHS with ``ApprovalRequired`` comes back ``Pending``. Every later call
then gets 403 until BLConfig approves it. After that, ``isSecured`` may
still be true. The import then saves the secured sample and stops.

The UUID and private PEM stay on the Home Assistant config entry so a
later import reuses the same BHS device. YAML export writes them when
all three are stored. The sample file contains the private key so the
reply can be decrypted later. That key is not sent on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

BHS_DEFAULT_PORT = 10014
BHS_DEVICE_NAME = "Home Assistant"
# The register call accepts a free-text platform, but "android" is seemingly the only value the BHS accepts.
BHS_PLATFORM = "android"
BHS_TIMEOUT_S = 15

_SDIM_SKIP_NAMES = frozenset(
    {"stop dim", "groepsreset dim", "groepssturing dim"}
)

_KIND_LABEL = {
    "rlm": ("RLM", "RLM"),
    "shutter": ("cover", "rolluik"),
    "dimmer": ("Dimmer", "Dimmer"),
    "softm": ("SoftM", "SoftM"),
    "sfeer": ("Sfeer", "Sfeer"),
    "tsm": ("TSM", "TSM"),
    "ldm": ("LDM", "LDM"),
    "wsm": ("WSM", "WSM"),
    "rtc": ("RTC", "RTC"),
    "aud": ("AUD", "AUD"),
    "bm8": ("BM8", "BM8"),
}


class BhsError(Exception):
    """A BHS call failed."""


class BhsConnectionError(BhsError):
    """The BHS host could not be reached."""


class BhsPendingError(BhsError):
    """The device is registered and waiting for BLConfig approval."""


class BhsSecuredError(BhsError):
    """This BHS has ISSECURE on. Encrypted REST is not implemented yet."""


class BhsBlockedError(BhsError):
    """BLConfig blocked this device."""


class BhsApiError(BhsError):
    """The BHS returned an error body or an unexpected payload."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def normalize_host(host: str) -> str:
    """Strip a scheme and a trailing slash. Port stays a separate field."""
    text = str(host or "").strip()
    lowered = text.lower()
    for prefix in ("http://", "https://"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.split("/")[0].rstrip("/")


def generate_device_credentials() -> tuple[str, str, str]:
    """UUID v4 plus RSA-2048 PKCS#8 private PEM and SPKI public PEM.

    Matches the openssl example in the BHS API docs: 2048-bit RSA, PEM
    public key with BEGIN PUBLIC KEY lines. A secured getMembers body
    uses PKCS#1 v1.5 (not OAEP) with the BHS public key.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return str(uuid4()), private_pem, public_pem


def public_pem_from_private(private_pem: str) -> str:
    """SPKI public PEM matching a stored PKCS#8 private key."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(
        private_pem.encode("ascii"), password=None
    )
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def encrypt_bhs_body(plaintext: str, bhs_public_pem: str) -> str:
    """Hybrid blob for one secured request.

    Part 1 is RSA-2048 PKCS#1 v1.5 of ``base64(aesKey)|base64(iv)``.
    Part 2 is base64 of AES-256-CBC (PKCS#7) ciphertext. The parts are
    joined with CRLF, ``---``, CRLF. Content-Type stays application/json.
    """
    import base64
    import os

    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    aes_key = os.urandom(32)
    iv = os.urandom(16)
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    part2 = base64.b64encode(ciphertext).decode("ascii")
    line = (
        base64.b64encode(aes_key).decode("ascii")
        + "|"
        + base64.b64encode(iv).decode("ascii")
    )
    public_key = serialization.load_pem_public_key(bhs_public_pem.encode("ascii"))
    wrapped = public_key.encrypt(line.encode("ascii"), asym_padding.PKCS1v15())
    part1 = base64.b64encode(wrapped).decode("ascii")
    return part1 + "\r\n---\r\n" + part2


def format_secure_dump(
    *,
    host: str,
    port: int,
    device_id: str,
    private_pem: str,
    sample: SecureSample,
) -> str:
    """Text dump for the developer. Includes the private key on purpose."""
    return (
        "B-Logicx secured BHS sample\n"
        f"host: {host}\n"
        f"port: {port}\n"
        f"device_id: {device_id}\n"
        "private_key:\n"
        f"{private_pem.strip()}\n"
        "\n"
        "POST /api/members/getMembers\n"
        "Content-Type: application/json\n"
        f"{sample.request_body}\n"
        "\n"
        f"response status: {sample.status}\n"
        f"response Content-Type: {sample.content_type}\n"
        f"{sample.response_text}"
    )


def _version_head(version: Any) -> str:
    text = str(version or "").strip()
    head, _, _ = text.partition("_")
    return head.casefold()


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _kind_word(kind: str, lang: str) -> str:
    pair = _KIND_LABEL.get(kind, (kind, kind))
    return pair[1] if lang == "nl" else pair[0]


def leftover_line(
    group: int | None,
    address: int | None,
    name: str,
    version: str,
    member_type: Any,
) -> str:
    loc = (
        f"{group}.{address}"
        if group is not None and address is not None
        else "?"
    )
    label = name or ""
    ver = version or "?"
    return f"{loc} {label} — {ver} (type {member_type})".strip()


@dataclass(frozen=True)
class _Row:
    group: int
    address: int
    name: str
    version: str
    member_type: int | None
    member_id: str


@dataclass(frozen=True)
class ImportCandidate:
    """One checkbox: a single address, a cover pair, or a Sfeer room."""

    key: str
    kind: str
    label: str
    entry: dict[str, Any]
    pairs: tuple[tuple[int, int], ...]


@dataclass
class ClassifyResult:
    candidates: list[ImportCandidate] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    leftover: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SecureSample:
    """Raw secured getMembers exchange. Members are not parsed."""

    status: int
    content_type: str
    request_body: str
    response_text: str


def _cover_role(name: str) -> str | None:
    text = name.casefold()
    if text.endswith("_op") or "_op_" in text:
        return "open"
    if text.endswith("_neer") or "_neer_" in text:
        return "close"
    return None


def _assign_open_close(first: _Row, second: _Row) -> tuple[_Row, _Row]:
    role_a = _cover_role(first.name)
    role_b = _cover_role(second.name)
    if role_a == "open" and role_b != "open":
        return first, second
    if role_b == "open" and role_a != "open":
        return second, first
    if role_a == "close" and role_b != "close":
        return second, first
    if role_b == "close" and role_a != "close":
        return first, second
    if first.address <= second.address:
        return first, second
    return second, first


def _cover_name(open_row: _Row, close_row: _Row) -> str:
    for row, suffix in ((open_row, "_OP"), (close_row, "_NEER")):
        name = row.name
        if name.upper().endswith(suffix):
            stripped = name[: -len(suffix)].rstrip("_- ")
            if stripped:
                return stripped
    return open_row.name or f"Cover {open_row.group}.{open_row.address}"


def _label(kind: str, loc: str, name: str, lang: str) -> str:
    word = _kind_word(kind, lang)
    if name:
        return f"{loc} {name} — {word}"
    return f"{loc} — {word}"


def _rows_from_members(members: list[Any]) -> tuple[list[_Row], list[str]]:
    leftover: list[str] = []
    dicts = [m for m in members if isinstance(m, dict)]
    require_id = any(str(m.get("memberID") or "").strip() for m in dicts)
    rows: list[_Row] = []
    for member in dicts:
        group = _as_int(member.get("group"))
        address = _as_int(member.get("address"))
        name = str(member.get("name") or "").strip()
        version = str(member.get("version") or "").strip()
        member_id = str(member.get("memberID") or "").strip()
        member_type = _as_int(member.get("memberType"))
        if require_id and not member_id:
            leftover.append(
                leftover_line(group, address, name, version, member.get("memberType"))
            )
            continue
        if group is None or address is None:
            leftover.append(
                leftover_line(group, address, name, version, member.get("memberType"))
            )
            continue
        rows.append(
            _Row(
                group=group,
                address=address,
                name=name,
                version=version,
                member_type=member_type,
                member_id=member_id,
            )
        )
    return rows, leftover


def classify_members(
    members: list[Any],
    occupied: set[tuple[int, int]] | None = None,
    *,
    lang: str = "en",
) -> ClassifyResult:
    """Turn a getMembers list into checkbox rows, already-present, and leftover."""
    known = occupied or set()
    result = ClassifyResult()
    rows, leftover = _rows_from_members(members)
    result.leftover.extend(leftover)
    used: set[tuple[int, int]] = set()

    type20 = sorted(
        (
            row
            for row in rows
            if row.member_type == 20 and _version_head(row.version) == "rlm"
        ),
        key=lambda row: (row.group, row.address),
    )
    i = 0
    while i < len(type20):
        current = type20[i]
        if i + 1 < len(type20):
            nxt = type20[i + 1]
            if nxt.group == current.group and nxt.address == current.address + 1:
                open_row, close_row = _assign_open_close(current, nxt)
                loc = (
                    f"{open_row.group}.{open_row.address}"
                    f"–{close_row.group}.{close_row.address}"
                )
                name = _cover_name(open_row, close_row)
                candidate = ImportCandidate(
                    key=(
                        f"shutter:{open_row.group}.{open_row.address}"
                        f":{close_row.group}.{close_row.address}"
                    ),
                    kind="shutter",
                    label=_label("shutter", loc, name, lang),
                    entry={
                        "type": "shutter",
                        "name": name,
                        "open_group": open_row.group,
                        "open_address": open_row.address,
                        "close_group": close_row.group,
                        "close_address": close_row.address,
                    },
                    pairs=(
                        (open_row.group, open_row.address),
                        (close_row.group, close_row.address),
                    ),
                )
                used.add((current.group, current.address))
                used.add((nxt.group, nxt.address))
                if known.intersection(candidate.pairs):
                    result.already.append(candidate.label)
                else:
                    result.candidates.append(candidate)
                i += 2
                continue
        result.leftover.append(
            leftover_line(
                current.group,
                current.address,
                current.name,
                current.version,
                current.member_type,
            )
        )
        used.add((current.group, current.address))
        i += 1

    sdim_moods: dict[int, list[_Row]] = {}
    for row in rows:
        if (row.group, row.address) in used:
            continue
        if row.member_type != 19 or _version_head(row.version) != "sdim":
            continue
        used.add((row.group, row.address))
        name_cf = row.name.casefold()
        if (
            row.address == 220
            or name_cf in _SDIM_SKIP_NAMES
            or "record" in name_cf
        ):
            result.leftover.append(
                leftover_line(
                    row.group, row.address, row.name, row.version, row.member_type
                )
            )
            continue
        sdim_moods.setdefault(row.group, []).append(row)

    for group, moods in sorted(sdim_moods.items()):
        pairs = tuple((group, mood.address) for mood in moods)
        name = f"Sfeer {group}"
        loc = str(group)
        candidate = ImportCandidate(
            key=f"sfeer:{group}",
            kind="sfeer",
            label=_label("sfeer", loc, name, lang),
            entry={
                "type": "sfeer",
                "name": name,
                "group": group,
                "moods": [
                    {
                        "name": mood.name or f"{group}.{mood.address}",
                        "address": mood.address,
                    }
                    for mood in moods
                ],
            },
            pairs=pairs,
        )
        if known.intersection(candidate.pairs):
            result.already.append(candidate.label)
        else:
            result.candidates.append(candidate)

    for row in rows:
        if (row.group, row.address) in used:
            continue
        used.add((row.group, row.address))
        kind: str | None = None
        head = _version_head(row.version)
        if row.member_type == 1 and head == "rlm":
            kind = "rlm"
        elif row.member_type == 2 and head == "dim1k":
            kind = "dimmer"
        elif row.member_type == 4 and head == "softm":
            kind = "softm"
        elif row.member_type == 3:
            # An INM has nothing this integration can read.
            continue
        elif row.member_type == 17:
            # An EXU sends the commands programmed into it when its external
            # input goes electrically high. That input is any boolean
            # signal. Set on the EXU address forces the input high and
            # holds it until Reset, so a toggle can leave the module stuck
            # out of normal mode. The import drops it.
            continue
        elif row.member_type == 7 and head == "tsm":
            kind = "tsm"
        elif row.member_type == 11 and head == "ldm":
            kind = "ldm"
        elif row.member_type == 13 and head == "wsm":
            kind = "wsm"
        elif row.member_type == 26:
            kind = "aud"
        elif row.member_type == 28:
            kind = "bm8"
        elif head == "rtc":
            kind = "rtc"
        if kind is None:
            # A member type this integration does not configure is dropped.
            continue
        loc = f"{row.group}.{row.address}"
        entry = {
            "type": kind,
            "name": row.name or loc,
            "group": row.group,
            "address": row.address,
        }
        if kind == "aud":
            entry["controller"] = "bhs"
        candidate = ImportCandidate(
            key=f"{kind}:{row.group}.{row.address}",
            kind=kind,
            label=_label(kind, loc, row.name, lang),
            entry=entry,
            pairs=((row.group, row.address),),
        )
        if known.intersection(candidate.pairs):
            result.already.append(candidate.label)
        else:
            result.candidates.append(candidate)
    return result


class BhsClient:
    """HTTP calls against ``http://host:port/api``. Session is duck-typed."""

    def __init__(self, session: Any, host: str, port: int, device_id: str) -> None:
        self._session = session
        self._host = normalize_host(host)
        self._port = int(port)
        self._device_id = str(device_id).strip()
        self._base = f"http://{self._host}:{self._port}/api"

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"x-device-id": self._device_id}
        json_body: dict[str, Any] | None = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            json_body = {} if body is None else body
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                headers=headers,
                json=json_body,
                timeout=BHS_TIMEOUT_S,
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except (TypeError, ValueError):
                    payload = {}
                status = int(response.status)
        except BhsError:
            raise
        except Exception as err:
            raise BhsConnectionError("Unable to communicate with the BHS") from err
        if not isinstance(payload, dict):
            payload = {}
        error_text = str(payload.get("error") or "").casefold()
        if status == 409 and path == "/device/register":
            return payload
        if status == 403 or "pending" in error_text:
            if "block" in error_text:
                raise BhsBlockedError("This device is blocked in BLConfig")
            raise BhsPendingError("This device is waiting for approval in BLConfig")
        if "block" in error_text and status >= 400:
            raise BhsBlockedError("This device is blocked in BLConfig")
        if status == 401:
            raise BhsApiError("unknown device", status=status)
        if "encryption" in error_text:
            raise BhsSecuredError("This BHS encrypts the API (ISSECURE)")
        if status >= 400:
            raise BhsApiError(error_text or "request failed", status=status)
        if "response" in payload and "members" not in payload and "isSecure" not in payload:
            raise BhsSecuredError("This BHS encrypts the API (ISSECURE)")
        if "error" in payload:
            raise BhsApiError(str(payload["error"]), status=status)
        return payload

    async def register(self, public_pem: str) -> str:
        """Register this UUID. Returns Approved, Pending, or Blocked."""
        payload = await self._request(
            "POST",
            "/device/register",
            {
                "name": BHS_DEVICE_NAME,
                "publicKey": public_pem,
                "platf": BHS_PLATFORM,
            },
        )
        if str(payload.get("error") or "").casefold() == "device already registered":
            return "Approved"
        status = str(payload.get("status") or "Approved").strip() or "Approved"
        folded = status.casefold()
        if folded == "blocked":
            raise BhsBlockedError("This device is blocked in BLConfig")
        if folded == "pending":
            return "Pending"
        return "Approved"

    async def is_secured(self) -> bool:
        payload = await self._request("GET", "/bhs/isSecured")
        if payload.get("isSecure") is True:
            return True
        if payload.get("isSecure") is False:
            return False
        raise BhsApiError("Unexpected isSecured response")

    async def get_members(self) -> list[dict[str, Any]]:
        payload = await self._request("POST", "/members/getMembers", {})
        members = payload.get("members")
        if not isinstance(members, list):
            raise BhsApiError("Unexpected getMembers response")
        return [m for m in members if isinstance(m, dict)]

    async def get_public_key(self) -> str:
        payload = await self._request("GET", "/bhs/getPublicKey")
        pem = str(payload.get("publicKey") or "").strip()
        if "BEGIN PUBLIC KEY" not in pem:
            raise BhsApiError("Unexpected getPublicKey response")
        return pem

    async def capture_secured_members(self) -> SecureSample:
        """POST the encrypted ``{}`` and return the raw reply, errors included."""
        public_pem = await self.get_public_key()
        body = encrypt_bhs_body("{}", public_pem)
        headers = {
            "x-device-id": self._device_id,
            "Content-Type": "application/json",
        }
        try:
            async with self._session.request(
                "POST",
                f"{self._base}/members/getMembers",
                headers=headers,
                data=body,
                timeout=BHS_TIMEOUT_S,
            ) as response:
                response_text = await response.text()
                response_headers = getattr(response, "headers", None)
                content_type = ""
                if response_headers is not None:
                    content_type = str(
                        response_headers.get("Content-Type", "") or ""
                    )
                status = int(response.status)
        except BhsError:
            raise
        except Exception as err:
            raise BhsConnectionError("Unable to communicate with the BHS") from err
        return SecureSample(
            status=status,
            content_type=content_type,
            request_body=body,
            response_text=response_text,
        )


async def read_member_list(client: BhsClient) -> list[dict[str, Any]] | SecureSample:
    """Cleartext member list, or a secured sample when ISSECURE is on.

    A list means the caller classifies and imports. A ``SecureSample``
    means the caller writes the dump and stops.
    """
    if await client.is_secured():
        return await client.capture_secured_members()
    return await client.get_members()
