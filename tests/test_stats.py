from math import isfinite
from unittest.mock import Mock

import hypothesis.strategies as st
from hypothesis import given

import aka_stats.stats as stats_module
from aka_stats.stats import Stats, value_to_float


def test_stats_class(monkeypatch):

    write_stat_mock = Mock()

    monkeypatch.setattr(stats_module, "write_stat", write_stat_mock)

    with Stats() as stat:
        stat("test", 2.0)
        stat("test", 2.0)
        assert not write_stat_mock.called
        stat("test", 2.0)

    assert write_stat_mock.call_count == 3


@given(st.binary())
def test_value_to_float_binary(value):

    try:
        expected_val = float(value)
        assert expected_val == value_to_float(value)
    except ValueError:
        assert value_to_float(value) is None


@given(st.booleans())
def test_value_to_float_booleans(value):
    assert value_to_float(value) is None


@given(st.text())
def test_value_to_float_text(value):

    try:
        expected_val = float(value)
        assert expected_val == value_to_float(value)
    except ValueError:
        assert value_to_float(value) is None


@given(st.complex_numbers())
def test_value_to_float_complex_numbers(value):
    assert value_to_float(value) is None


@given(st.floats())
def test_value_to_float_floats(value):
    if isfinite(value):
        assert value_to_float(str(value)) == value
    else:
        assert value_to_float(str(value)) is None


def test_catching_exception_stats(monkeypatch):

    write_stat_mock = Mock()
    monkeypatch.setattr(stats_module, "write_stat", write_stat_mock)

    try:
        with Stats():
            raise ValueError("Error")
    except ValueError:
        pass

    write_stat_mock.call_count == 2

    assert list(sorted(["errors__all", "errors__EXC:ValueError"])) == list(
        sorted([call[0][1] for call in write_stat_mock.call_args_list])
    )


def test_exception_stats(monkeypatch):

    write_stat_mock = Mock()
    monkeypatch.setattr(stats_module, "write_stat", write_stat_mock)

    with Stats() as stats:
        try:
            raise ValueError("Error")
        except ValueError as e:
            stats.exception(e)

    write_stat_mock.call_count == 2

    assert list(sorted(["errors__all", "errors__EXC:ValueError"])) == list(
        sorted([call[0][1] for call in write_stat_mock.call_args_list])
    )
