"""
# Mock Stats

This module contains a pytest fixture for mocking the stats object.

Example of usage:

```python
import aka_stats.testing  # add fixture to scope


def do_something():

    with Stats() as stat:
        ...
        stat("test", 1)


def test_do_something(mock_stats):

    do_something()

    assert len(mock_stats) == 1
```
"""
try:
    from pytest import fixture
except ImportError:

    def fixture(func):
        return func


from typing import AnyStr, List, Tuple
from aka_stats import Stats
import aka_stats
import aka_stats.stats


class MockStats(Stats):
    """Class to disable writing to redis.

    It should not be used directly just subclassed like in the fixture below in `mock_stats`

    """

    def write_mock_stat(self, stat: Tuple[float, str, aka_stats.stats.Number, AnyStr]):
        raise NotImplementedError("MockStats should not be used directly.")

    async def save_stats_async(self):
        self.save_stats()

    def save_stats(self):
        [self.write_mock_stat(stat) for stat in self.recorded_stats]
        self.recorded_stats = []


@fixture
def mock_stats(monkeypatch) -> List[Tuple[float, str, aka_stats.stats.Number, AnyStr]]:
    """Fixture to mock stats."""
    recorded_stats = []

    class MyMockStats(MockStats):
        def write_mock_stat(self, stat):
            recorded_stats.append(stat)

    monkeypatch.setattr(aka_stats, "Stats", MyMockStats)
    monkeypatch.setattr(aka_stats.stats, "Stats", MyMockStats)

    return recorded_stats
