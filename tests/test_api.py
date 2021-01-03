import asyncio
from collections import defaultdict
from datetime import datetime
from fnmatch import fnmatch
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from aka_stats.api import STAT_NAMES, app as stats_app
from aka_stats.prometheus import generate_metrics, stat_formatter
from aka_stats.redis import async_redis
from aka_stats.settings import config


class MockRedis:
    def __init__(self):
        self.me = {}
        self.removed_from_sets = defaultdict(list)

    async def get(self, key: str) -> Optional[bytes]:
        try:
            return self.me[key]
        except KeyError:
            return None

    async def lrange(self, key, start, end):
        try:
            return self.me[key][start:end]
        except KeyError:
            return []

    async def scan(self, cursor: bytes, match: str = "") -> Tuple[int, List[bytes]]:
        normalized_cursor = int(cursor)
        matched_keys = [key for key in self.me.keys() if fnmatch(key, match)]
        if not matched_keys:
            return 0, []
        return (
            normalized_cursor + 1 if normalized_cursor + 1 < len(matched_keys) else 0,
            [matched_keys[normalized_cursor].encode("utf8")],
        )

    async def izscan(self, key: str, match: str = "*") -> AsyncIterator[str]:
        """
        Emulate ZSCAN, usually it should work on a field, but I emulate here a situation where the stats
        were added by the aka_stats and the stat names were added to {STAT_NAMESPACE}::INDEX
        """
        keys = (key.split("::")[-1] for key in self.me.keys() if "::HISTORY::" in key)
        matched_keys = [key for key in keys if fnmatch(key, match)]
        for k in matched_keys:
            await asyncio.sleep(0)
            yield k.encode("utf8"), 1

    async def zrem(self, key, label) -> AsyncIterator[str]:
        self.removed_from_sets[key].append(label)
        return 1

    def close(self):
        pass

    async def wait_closed(self):
        pass


@pytest.fixture
def redis() -> Iterator[MockRedis]:

    redis = MockRedis()

    async def make_connection(*_, **__):
        return redis, redis

    async_redis.attach(redis, redis)

    yield redis


@pytest.fixture(scope="session")
def client() -> TestClient:

    app = FastAPI()
    app = stats_app.attach_routes(app)
    client = TestClient(app, base_url="http://127.0.0.1/")
    return client


def test_attaching():

    app = FastAPI()
    app = stats_app.attach_routes(app)

    available_paths = [route.path for route in app.routes]  # type: ignore

    stat_paths = [map[2] for map in stats_app.maps]

    for stat_path in stat_paths:
        assert stat_path in available_paths


def test_available_stats(redis, client):

    for i in range(10):
        redis.me[f"{config.namespace}::HISTORY::test{i}"] = []

    response = client.get("/api/v1/available-stats")

    assert len(response.json()) == 10


def make_stat_keys(label: str) -> List[str]:
    return [f"{config.namespace}::{stat_name.upper()}::{label}" for stat_name in STAT_NAMES | {"history"}]


def test_stats_fetching(redis, client):

    [redis.me.update({key: b"0.0"}) for key in make_stat_keys("test1")]

    response = client.get("/api/v1/stats/test1")
    stats = response.json()

    assert len(stats.keys()) == len(STAT_NAMES)

    for stat_name in STAT_NAMES:
        assert stats[stat_name] == 0.0


def test_stats_fetching_not_there(redis: MockRedis, client):

    response = client.get("/api/v1/stats/test1")
    assert response.status_code == 200
    assert len(response.json()) == 0
    assert redis.removed_from_sets["AKA-STATS::INDEX"] == ["test1"]


def test_stats_history(redis, client):

    dtime = datetime(2020, 4, 6)

    redis.me[f"{config.namespace}::HISTORY::test_abc"] = [f"{dtime.timestamp()};0.0".encode("utf8")]
    response = client.get("/api/v1/stats-history/test_abc")

    history = response.json()[0]

    assert history["timestamp"] == dtime.timestamp()
    assert history["label"] == "test_abc"
    assert history["value"] == 0.0


def test_stats_history_not_there(redis, client):

    response = client.get("/api/v1/stats-history/test_abc")
    history = response.json()
    assert not history


def test_stats_prometheus_export(redis, client):

    [redis.me.update({key: b"0.0" if "COUNT" not in key else b"1"}) for key in make_stat_keys("test:1")]

    @stat_formatter("test:")
    def formatter(key: str, stat: Dict[str, Any]):
        _, id_ = key.split(":", 1)
        return generate_metrics({"id": id_}, stat, "TEST_STAT", ["count", "max", "min", "last"])

    response = client.get("/api/v1/stats-prometheus")
    lines = list(sorted(response.text.splitlines()))
    assert len(lines) == 4

    assert lines[0].strip() == 'TEST_STAT_COUNT{id="1"} 1.0'
    assert lines[1].strip() == 'TEST_STAT_LAST{id="1"} 0.0'
    assert lines[2].strip() == 'TEST_STAT_MAX{id="1"} 0.0'
    assert lines[3].strip() == 'TEST_STAT_MIN{id="1"} 0.0'
