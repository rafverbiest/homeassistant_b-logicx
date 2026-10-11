"""BL-BM8 chime numbers and the Data address each one sends."""

import pytest

from const import (
    BM8_DATA_GROUP,
    BM8_STOP_DATA_ADDRESS,
    bm8_chime_data_address,
    bm8_data_address_allowed,
)


def test_chime_numbers_map_onto_data_addresses():
    assert BM8_DATA_GROUP == 0
    assert [bm8_chime_data_address(n) for n in range(1, 9)] == list(range(2, 10))
    assert BM8_STOP_DATA_ADDRESS == 10


def test_only_chime_and_stop_data_addresses_are_sent():
    for data_address in range(2, 11):
        assert bm8_data_address_allowed(data_address)
    for data_address in (0, 1, 11, -1, True, False, None, "2"):
        assert not bm8_data_address_allowed(data_address)


def test_chime_number_outside_1_to_8_is_rejected():
    for chime in (0, 9, -1, True, None, "1"):
        with pytest.raises(ValueError):
            bm8_chime_data_address(chime)
