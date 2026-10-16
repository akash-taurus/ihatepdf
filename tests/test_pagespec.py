"""Page-spec and page-order parser tests."""

from __future__ import annotations

import pytest

from core.pagespec import parse_order, parse_pagespec, parse_ranges_for_split


def test_pagespec_all_pages_when_empty():
    assert parse_pagespec(None, 4) == [0, 1, 2, 3]
    assert parse_pagespec("", 3) == [0, 1, 2]
    assert parse_pagespec("   ", 2) == [0, 1]


def test_pagespec_single_range_and_list():
    assert parse_pagespec("1", 5) == [0]
    assert parse_pagespec("1-3", 5) == [0, 1, 2]
    assert parse_pagespec("1,3-5", 5) == [0, 2, 3, 4]
    # duplicates and out-of-order input are normalised
    assert parse_pagespec("3,1,3", 5) == [0, 2]
    assert parse_pagespec("5-3", 5) == [2, 3, 4]


@pytest.mark.parametrize("spec", ["0", "6-7", "1-", "-2", "abc", ",", "1,,x"])
def test_pagespec_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        parse_pagespec(spec, 5)


def test_order_preserves_input_and_allows_subset():
    assert parse_order("3,1,2", 3) == [2, 0, 1]
    assert parse_order("2,2,1", 3) == [1, 1, 0]  # repeats duplicate a page
    assert parse_order("5-3", 5) == [4, 3, 2]
    assert parse_order("4,1", 5) == [3, 0]  # subset keeps only listed pages


@pytest.mark.parametrize("spec", ["", "  ", "0", "9", "1,x"])
def test_order_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        parse_order(spec, 4)


def test_split_ranges():
    assert parse_ranges_for_split(None, 3) == [[0], [1], [2]]
    assert parse_ranges_for_split("1-2,3", 3) == [[0, 1], [2]]
    assert parse_ranges_for_split("3-2", 3) == [[1, 2]]
    with pytest.raises(ValueError):
        parse_ranges_for_split("1-9", 3)
