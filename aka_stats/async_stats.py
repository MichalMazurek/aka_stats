from typing import AsyncIterator, Dict, List, Optional

from aka_stats.redis import async_redis
from aka_stats.settings import config
from aka_stats.stats import STAT_NAMES, Stat, StatsData, parse_stat, value_to_float


class NotFoundError(Exception):
    pass


async def stat_history(label: str, prefix: str = config.namespace) -> List[Stat]:
    """Give a list of stats for the stat name in a prefix

    Args:
        label (str): name of the stat
        prefix (str, optional): prefix name. Defaults to `config.namespace`.

    Returns:
        List[Stat]: list of stats
    """
    async with async_redis() as (reader, _):
        stats = await reader.lrange(f"{prefix}::HISTORY::{label}", 0, config.history_size)
        return [parse_stat(label, stat) for stat in stats]


async def fetch_stats(label: str, prefix: str = config.namespace) -> Optional[StatsData]:
    f"""Fetch stats data from redis, data contain all the stats: {STAT_NAMES}
    Args:
        label (str): stats label
        prefix (str, optional): prefix name. Defaults to config.namespace.
    Returns:
        Optional[StatsData]
    """

    async with async_redis() as (reader, writer):
        stats_to_retrieve = [(stat_name, f"{prefix}::{stat_name.upper()}::{label}") for stat_name in STAT_NAMES]
        # TODO: use mget here
        stats = {stat_name: value_to_float(await reader.get(redis_key)) for stat_name, redis_key in stats_to_retrieve}
        if list(stats.values()).pop() is None:
            # try to remove the label from index as the stat is no longer present in Redis, or wasn't there in the
            # first place, no other way of cleanup for now
            await writer.zrem(f"{prefix}::INDEX", str(label))
            return None
        return StatsData(**stats)


async def available_stats(matcher: str = "*", prefix: str = config.namespace) -> AsyncIterator[str]:
    """Fetch a list of available stats in Redis.

    Warning: you can get duplicates here

    Args:
        prefix (str): prefix for stats
    Returns:
        AsyncIterator[str] - list with names
    """
    async with async_redis() as (reader, _):
        async for key, _ in reader.izscan(f"{prefix}::INDEX", match=str(matcher)):
            yield key.decode("utf8")


async def contexts(context_ids: List[str], prefix: str = config.namespace) -> Dict[str, bytes]:
    """Retrieve context by ids

    Args:
        context_ids (List[str]): list of context md5 ids

    Returns:
        Dict[str, str]: context dictionary
    """
    async with async_redis() as (reader, _):
        return {
            c_id: ctx
            for c_id, ctx in zip(context_ids, await reader.mget(*[f"{prefix}::CONTEXTS::{cid}" for cid in context_ids]))
            if ctx
        }
