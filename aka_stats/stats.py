import logging
import sys
import traceback
from collections import namedtuple
from datetime import datetime
from hashlib import md5
from math import isfinite
from typing import Any, AnyStr, Dict, List, Optional, Union, cast

import pytz

from aka_stats.redis import AioRedis, async_redis, sync_redis
from aka_stats.settings import config

STAT_NAMES = {"count", "avg", "stdev", "max", "min", "total", "last", "last_time"}

TWO_WEEKS_IN_SECONDS = 604_800 * 2

LUA_STAT_SCRIPT = f"""
redis.call("LPUSH", KEYS[3] .. "::HISTORY::" .. KEYS[2], KEYS[4] .. ";" .. KEYS[1] .. ";" .. KEYS[5])
redis.call("LTRIM", KEYS[3] .. "::HISTORY::" .. KEYS[2], 0, {config.history_size-1})
redis.call("SET", KEYS[3] .. "::LAST::" .. KEYS[2], KEYS[1])
redis.call("SET", KEYS[3] .. "::LAST_TIME::" .. KEYS[2], KEYS[4])

local stat = tonumber(KEYS[1])
local count = tonumber(redis.call("INCR", KEYS[3] .. "::COUNT::" .. KEYS[2]))
local total = redis.call("INCRBYFLOAT", KEYS[3] .. "::TOTAL::".. KEYS[2], KEYS[1])
local avg = tonumber(total) / count

redis.call("SET", KEYS[3] .. "::AVG::" .. KEYS[2], tostring(avg))

local total_sq = redis.call("INCRBYFLOAT", KEYS[3] .. "::TOTAL_SQ::" .. KEYS[2], tostring(math.pow(stat, 2)))
local stdev

if count > 1 then
    stdev = math.sqrt( total_sq / (count - 1) - (count / (count-1)) * math.pow(avg, 2))
else
    stdev = 0
end

avg = tostring(avg)

stdev = tostring(stdev)

redis.call("SET", KEYS[3] .. "::STDEV::" .. KEYS[2], stdev)

local max = tonumber(redis.call("GET", KEYS[3] .."::MAX::".. KEYS[2])) or 0
max = tostring(math.max(max, stat))

redis.call("SET", KEYS[3] .. "::MAX::".. KEYS[2], max)

local min = tonumber(redis.call("GET", KEYS[3] .. "::MIN::".. KEYS[2])) or nil
if min == nil then
    min = stat
else
    min = tostring(math.min(min, stat))
end

redis.call("SET", KEYS[3] .. "::MIN::".. KEYS[2], min)

redis.call("EXPIRE", KEYS[3] .. "::MIN::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::MAX::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::AVG::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::STDEV::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::COUNT::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::TOTAL::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::TOTAL_SQ::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})
redis.call("EXPIRE", KEYS[3] .. "::HISTORY::".. KEYS[2], {TWO_WEEKS_IN_SECONDS})

redis.call("ZADD", KEYS[3] .. "::INDEX", 1, KEYS[2])

return stat .. ":" .. avg .. ":" .. stdev .. ":" .. max .. ":" .. min .. ":" .. total
"""

Number = Union[int, float]


DELIMITER = "_"

LINE_MAPPING = {",": DELIMITER, ";": DELIMITER, "=": DELIMITER, " ": DELIMITER, "\\": ""}


def hash_context(context: Optional[AnyStr] = None) -> str:
    """Create a md5 hash for the string or bytes, also bytes buffer object is supported.

    Args:
        context (Optional[AnyStr], optional): [description]. Defaults to None.

    Returns:
        str: hexdigest of the given context
    """
    if not context:
        return ""

    try:
        context_bytes = cast(str, context).encode("utf8")
    except AttributeError:
        context_bytes = cast(bytes, context)
    try:
        return md5(context_bytes).hexdigest()
    except TypeError:
        return hash_context(str(context))


def write_stat(
    timestamp: float, name: str, stat: Number, context: Optional[AnyStr] = None, prefix: str = config.namespace
):
    """Write a stat to Redis

    !!! Information about context:
        Please be aware that context will be stored in Redis only once, in history I am storing here only hash of that
        context, if you are storing in the context lot of data that is fine as long it doesn't change much.
        So what to store then? For sure I would not not store timestamps, as this is kept in history. I would store
        things that are needed to get the context, but are more static, I would also store keys in order


    Args:
        timestamp (float): timestamp for history
        name (str): name of the stat
        stat (Number): stat value, int or float
        context (AnyStr, optional): context for the stat
        prefix (str, optional): prefix for redis keys. Defaults to config.namespace.
    """
    with sync_redis() as (reader, writer):
        context_id = hash_context(context)
        writer.eval(LUA_STAT_SCRIPT, 5, stat, name, prefix, timestamp, context_id)
        if context:
            context_key = f"{prefix}::CONTEXTS::{context_id}"
            writer.set(context_key, context, nx=True)
            writer.expire(context_key, TWO_WEEKS_IN_SECONDS)


async def write_stat_async(
    timestamp: float, name: str, stat: Number, context: Optional[AnyStr] = None, prefix: str = config.namespace
):
    """Write a stat to Redis

    Args:
        timestamp (float): timestamp for history
        name (str): name of the stat
        stat (Number): stat value, int or float
        prefix (str, optional): prefix for redis keys. Defaults to config.namespace.
    """
    async with async_redis() as (reader, writer):
        context_id = hash_context(context)
        await writer.eval(LUA_STAT_SCRIPT, keys=[stat, name, prefix, timestamp, context_id])
        if context:
            context_key = f"{prefix}::CONTEXTS::{context_id}"
            await writer.set(context_key, context, exist=AioRedis.SET_IF_NOT_EXIST)
            await writer.expire(context_key, TWO_WEEKS_IN_SECONDS)


def now_timestamp() -> float:
    """Timestamp for now, timezone according to Settings.timezone

    Returns:
        float: the timestamp
    """
    return datetime.now(tz=PREFERRED_TIMEZONE).timestamp()


def safe_string(value: str, mapping=LINE_MAPPING) -> str:
    """Return string where characters matching the mapping are replaced with the value.

    Args:
        value (str): string value to check
        mapping (dict): map characters to their replacement character

    Returns:
        str: updated string value

    Examples:
        >>> safe_string('alreadysafe')
        'alreadysafe'
        >>> safe_string('filter_commas,and;semicolons')
        'filter_commas_and_semicolons'
    """
    return "".join(mapping.get(i, i) for i in value)


def dict_to_line_labels(labels: Dict[str, str]) -> str:
    """Convert a dict to a line label.

    Args:
        labels (Dict[str,str]): dictionary of lables

    Returns:
        str: labels string for stat label name

    """
    return ",".join(f"{safe_string(key)}={safe_string(value)}" for key, value in labels.items())


class Stats:
    """Records all the stats, and gives an interface to save them to Redis.

    Stats context manager, records stats and on exit puts them in Redis.

    Try not to hold lot of stats in one go.

    Example:
        >>> t = timer()
        >>> with Stats() as stat:
        >>>     for task in list_of_tasks:
        >>>         job(task)
        >>>         stat_value = next(t)
        >>>         stat(task['name'], stat_value.stat)


    """

    def __init__(
        self, prefix: str = config.namespace, log: Optional[logging.Logger] = None, disable_warnings: bool = False
    ):
        self.prefix = prefix
        self.recorded_stats = []
        self.log = log or logging.getLogger("Stats")
        self.disable_warnings = disable_warnings

    def __call__(
        self, label: str, value: Number, context: Optional[AnyStr] = None, extra_labels: Optional[Dict[str, str]] = None
    ):
        """Save stat for later

        Args:
            label (str): name of the stat
            value (Number): value of the stat
        """
        return self.stat(label, value, context, extra_labels)

    def get_exception_context(self):
        exc_ctx = traceback.format_exc()
        return exc_ctx

    def get_current_exception_type(self):
        return sys.exc_info()[0]

    def exception(
        self,
        exc_type: Union[type, Exception] = None,
        exc_value: Optional[Exception] = None,
        traceback: Optional[Any] = None,
        additional_labels: Optional[List[str]] = None,
        context: Optional[AnyStr] = None,
    ):
        """Save exception to stats

        Args:
            exc_type ([type]): [description]
            exc_value (Optional[str], optional): [description]. Defaults to None.
            traceback (Optional[Any], optional): [description]. Defaults to None.
            additional_labels (Optional[List[str]], optional): [description]. Defaults to None.
            context (Optional[AnyStr], optional): [description]. Defaults to None.
        """
        error_context = context or self.get_exception_context()
        additional_error_labels = additional_labels or []

        current_exc_type = exc_type or self.get_current_exception_type()

        if current_exc_type:
            exception_name = (
                current_exc_type.__name__ if current_exc_type.__class__ is type else current_exc_type.__class__.__name__
            )
            error_label = f"EXC:{exception_name}"
        else:
            error_label = "all"
            if not self.disable_warnings:
                self.log.warning("Got an empty call to exception.")

        self.error(error_label, *additional_error_labels, context=error_context)

    def error(self, *labels, context: Optional[AnyStr] = None):
        error_labels = set([f"errors__{label}" for label in labels + ("all",)])
        [self.stat(error_label, 1.0, context) for error_label in error_labels]

    def stat(
        self, label: str, value: Number, context: Optional[AnyStr] = None, extra_labels: Optional[Dict[str, str]] = None
    ):
        """Save stat for later

        Args:
            label (str): name of the stat
            value (Number): value of the stat
        """
        if extra_labels:
            label = f"{label};{dict_to_line_labels(extra_labels)}"
        self.recorded_stats.append((now_timestamp(), label, value, context))

    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.exception(exc_type, exc_value, traceback)
        self.save_stats()

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.exception(exc_type, exc_value, traceback)

        await self.save_stats_async()

    async def save_stats_async(self):
        [await write_stat_async(*stat, prefix=self.prefix) for stat in self.recorded_stats]
        self.recorded_stats = []

    def save_stats(self):
        """Save stats to Redis."""
        [write_stat(*stat, prefix=self.prefix) for stat in self.recorded_stats]
        self.recorded_stats = []


def push_stat(label: str, value: Number, prefix: str = config.namespace):
    """Push one stat to the Redis

    Args:
        label (str): label of the stat
        value (Number): stat value
        prefix (str, optional): prefix for redis. Defaults to config.namespace.
    """
    write_stat(now_timestamp(), label, value, prefix)


async def push_stat_async(label: str, value: Number, prefix: str = config.namespace):
    """Push one stat to the Redis

    Args:
        label (str): label of the stat
        value (Number): stat value
        prefix (str, optional): prefix for redis. Defaults to config.namespace.
    """
    await write_stat_async(now_timestamp(), label, value, prefix)


PREFERRED_TIMEZONE = pytz.timezone(config.timezone)

HISTORY_STAT_FIELDS = ["timestamp", "label", "value", "context_id"]

Stat = namedtuple("Stat", HISTORY_STAT_FIELDS)


def parse_stat(label: str, stat: bytes) -> Stat:
    """Parse bytes from Redis with stat info

    Args:
        label (str): name of the stat
        stat (bytes): stat from redis list

    Returns:
        Stat: named tuple with timestamp, label and value
    """
    stat_split = stat.decode("utf8").split(";")
    timestamp, value = [float(v) for v in stat_split[:2]]

    try:
        context_id = stat_split[2]
    except IndexError:
        context_id = ""

    return Stat(timestamp=timestamp, label=label, value=value, context_id=context_id)


def stat_history(label: str, prefix: str = config.namespace) -> List[Stat]:
    """Give a list of stats for the stat name in a prefix

    Args:
        label (str): name of the stat
        prefix (str, optional): prefix name. Defaults to config.namespace.

    Returns:
        List[Stat]: list of stats
    """
    with sync_redis() as (reader, _):
        stats = reader.lrange(f"{prefix}::HISTORY::{label}", 0, config.history_size)
        return [parse_stat(label, stat) for stat in stats]


StatsData = namedtuple("Stats", STAT_NAMES)


def value_to_float(value: Any) -> Union[float, None]:
    """Value to float or None if cannot convert.

    Args:
        value (Any): value to be converted

    Returns:
        Union[float, None]: converted value
    """
    try:
        if value is True or value is False or value == "":
            return None
        floated = float(value)
        return floated if isfinite(floated) else None
    except (TypeError, ValueError):
        return None


def fetch_stats(label: str, prefix: str = config.namespace) -> StatsData:
    f"""Fetch stats data from redis, data contain all the stats: {STAT_NAMES}
    Args:
        label (str): stats label
        prefix (str, optional): prefix name. Defaults to config.namespace.
    Returns:
        StatsData
    """

    with sync_redis() as (reader, _):
        stats_to_retrieve = [(stat_name, f"{prefix}::{stat_name.upper()}::{label}") for stat_name in STAT_NAMES]
        return StatsData(
            **{stat_name: value_to_float(reader.get(redis_key)) for stat_name, redis_key in stats_to_retrieve}
        )
