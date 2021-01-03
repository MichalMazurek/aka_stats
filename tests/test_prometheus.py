import time
from typing import Dict, Iterator, List

import hypothesis
import hypothesis.strategies as st
import pytest

import aka_stats.prometheus as prometheus_module
from aka_stats.prometheus import (
    dict_to_labels,
    escape_value,
    generate_metrics,
    parse_line_protocol_stat_key,
    prometheus_export,
    stat_formatter,
)
from aka_stats.stats import StatsData

TEST_STAT = [10, 20, 5, 10, 10, 4, 10]


def generate_stat(multiplier: int = 1) -> List[StatsData]:

    total = 0
    new_max = 0
    new_min = 10 ** 5
    for i, v in enumerate(TEST_STAT, 1):
        value = multiplier * v
        total += value
        avg = total / i

        new_max = max(value, new_max)
        new_min = min(value, new_min)

        yield StatsData(
            count=i, avg=avg, total=total, last=value, last_time=time.time(), stdev=0, max=new_max, min=new_min
        )


STATS = {"stat:1": list(generate_stat()), "stat:2": list(generate_stat(2)), "stat:3": list(generate_stat(3))}


async def available_stats_mock(matcher: str = "*"):

    for k in STATS.keys():
        yield k


async def fetch_stats_mock(stat_name: str):
    return STATS[stat_name][-1]


@pytest.mark.asyncio
async def test_prometheus_export(monkeypatch):
    """
    Testing exports
    """
    monkeypatch.setattr(prometheus_module, "available_stats", available_stats_mock)
    monkeypatch.setattr(prometheus_module, "fetch_stats", fetch_stats_mock)
    lines = [line async for line in prometheus_export()]

    assert len(lines) == 21

    @stat_formatter("stat:")
    def test_stat_formatter(key: str, stat_data: Dict[str, any]) -> Iterator[str]:
        _, host_id = key.split(":", 1)

        labels = {"host_id": host_id}
        return generate_metrics(labels, stat_data, "TEST_STAT", fields=["max", "last", "avg"])

    lines = [line async for line in prometheus_export()]

    assert len(lines) == 9

    for line in lines:
        assert line.startswith("TEST_STAT_")


@hypothesis.given(st.characters() | st.complex_numbers() | st.text())
def test_dict_to_labels_hypothesis(character: str):
    assert dict_to_labels({"test": character}) == '{test="' + f"{escape_value(character)}" + '"}'


@hypothesis.given(st.none())
def test_dict_to_labels_none(character: str):
    assert dict_to_labels({"test": character}) == '{test=""}'


def test_line_protocol_key_parser():

    assert parse_line_protocol_stat_key("POLLER;hostname=example.com,ip=10.0.0.1") == (
        "POLLER",
        {"hostname": "example.com", "ip": "10.0.0.1"},
    )


def test_line_prtocol_key_parser_empty():

    assert parse_line_protocol_stat_key("POLLER") == (
        "POLLER",
        {},
    )
