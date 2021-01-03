from collections import namedtuple
from time import time

from aka_stats.stats import Stats, push_stat

TimerStat = namedtuple("TimerStat", ["stat", "total"])


def timer():
    """Simple stat timer.

    Returns:
        Iterator[TimerStat]: generator for time stats

    """
    last_time = time()
    total = 0.0
    stat = 0.0

    def time_generator():
        nonlocal last_time, stat, total
        while True:
            current_time = time()
            stat = current_time - last_time
            total += stat
            last_time = current_time
            yield TimerStat(stat, total)

    return time_generator()


__all__ = ["timer", "Stats", "push_stat"]
