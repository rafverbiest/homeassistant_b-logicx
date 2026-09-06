"""Config-flow UX helpers: picker sort + translation key parity."""

from __future__ import annotations

import json
from pathlib import Path

from address_config import entries_sorted_for_picker


def test_entries_sorted_group_then_address():
    addresses = [
        {"type": "normal", "name": "Z", "group": 5, "address": 10},
        {"type": "normal", "name": "A", "group": 2, "address": 80},
        {
            "type": "shutter",
            "name": "Cover",
            "open_group": 3,
            "open_address": 1,
            "close_group": 3,
            "close_address": 2,
        },
        {
            "type": "sfeer",
            "name": "Living",
            "group": 5,
            "moods": [{"name": "TV", "group": 5, "address": 221}],
        },
        {"type": "readonly", "name": "PIR", "group": 1, "address": 8},
        {"type": "normal", "name": "B", "group": 2, "address": 17},
    ]
    sorted_addrs = entries_sorted_for_picker(addresses)
    names = [a["name"] for a in sorted_addrs]
    # group → address: 1.8, 2.17, 2.80, 3.1 cover, 5 sfeer, 5.10
    assert names == ["PIR", "B", "A", "Cover", "Living", "Z"]


def test_translation_files_key_parity():
    base = Path(__file__).resolve().parent.parent / "custom_components" / "b_logicx"
    en = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    nl = json.loads((base / "translations" / "nl.json").read_text(encoding="utf-8"))

    def leaves(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from leaves(v, f"{prefix}.{k}" if prefix else k)
        else:
            yield prefix

    assert set(leaves(en)) == set(leaves(nl))
    assert "selector.options_menu.options.add_sfeer_room" in set(leaves(en))
    assert "selector.address_type.options.shutter" in set(leaves(nl))
    assert "options.step.init.data.next_step_id" in set(leaves(en))
