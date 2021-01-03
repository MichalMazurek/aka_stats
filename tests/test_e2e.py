import os
from contextlib import suppress

import pytest
from pytest import fixture
from pytest_redis import factories

from aka_stats import Stats
from aka_stats.async_stats import available_stats
from aka_stats.prometheus import prometheus_export
from aka_stats.redis import async_redis
from aka_stats.settings import config

pytestmark = pytest.mark.skipif(os.getenv("SKIP_E2E", "0") == "1", reason="Skipping for gitlab pipeline")


redis_port = factories.get_port([10000, 30000])
redis_my_proc = factories.redis_proc(port=redis_port)
redis_my_db = factories.redisdb("redis_my_proc")


@fixture
async def real_redis(monkeypatch, redis_my_proc):
    monkeypatch.setattr(config, "redis_url", f"redis://127.0.0.1:{redis_port}")
    await async_redis.open_connection()

    yield redis_my_proc

    await async_redis.close()


@pytest.mark.asyncio
async def test_happy_scenario(real_redis):

    async with Stats() as stat:
        stat("test;host=localhost", 123)

    async with async_redis() as (reader, writer):
        assert len(await reader.keys(f"{config.namespace}::HISTORY::*")) == 1
        assert (await reader.zcard(f"{config.namespace}::INDEX")) == 1

    stats_generator = available_stats("*")

    available_stat = await stats_generator.__anext__()

    assert available_stat == "test;host=localhost"


@pytest.mark.asyncio
async def test_not_matched_stat_scenario(real_redis):
    stats_generator = available_stats("SOMETHING*")

    with pytest.raises(StopAsyncIteration):
        await stats_generator.__anext__()


@pytest.mark.asyncio
async def test_prometheus_stats(real_redis):

    async with Stats() as stat:
        stat("prometheus:test;host=example.com", 300)
        # using extra_labels is prefered as it make sure, the values and keys are being filtered for bad characters
        stat("prometheus:test_2", 600, extra_labels={"host": "example.com", "something": "labels"})

    lines = [line async for line in prometheus_export("prometheus:*")]
    assert len(lines) == 14

    expected_lines = [
        'prometheus:test_2_AVG{host="example.com",something="labels"} 600.0\n',
        'prometheus:test_2_COUNT{host="example.com",something="labels"} 1.0\n',
        'prometheus:test_2_LAST{host="example.com",something="labels"} 600.0\n',
        'prometheus:test_2_MAX{host="example.com",something="labels"} 600.0\n',
        'prometheus:test_2_MIN{host="example.com",something="labels"} 600.0\n',
        'prometheus:test_2_STDEV{host="example.com",something="labels"} 0.0\n',
        'prometheus:test_2_TOTAL{host="example.com",something="labels"} 600.0\n',
        'prometheus:test_AVG{host="example.com"} 300.0\n',
        'prometheus:test_COUNT{host="example.com"} 1.0\n',
        'prometheus:test_LAST{host="example.com"} 300.0\n',
        'prometheus:test_MAX{host="example.com"} 300.0\n',
        'prometheus:test_MIN{host="example.com"} 300.0\n',
        'prometheus:test_STDEV{host="example.com"} 0.0\n',
        'prometheus:test_TOTAL{host="example.com"} 300.0\n',
    ]
    assert list(sorted(lines)) == expected_lines


@pytest.mark.asyncio
async def test_error_stats(real_redis):

    test_list = []
    with suppress(IndexError):
        async with Stats():
            test_list[30]

    lines = [line async for line in prometheus_export("errors*")]

    expected_lines = ['AKA-STATS_ERROR_COUNT{EXC="IndexError"} 1.0\n', 'AKA-STATS_ERROR_COUNT{error="all"} 1.0\n']
    assert len(lines) == 2

    assert lines == expected_lines
