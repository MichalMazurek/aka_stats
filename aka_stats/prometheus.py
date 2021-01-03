"""
# Prometheus data formatting.

Data is stored in Redis is a format of `key` and `value`.

Default parser is using stat keys which can look like this:
`SNMP_POLLER;hostname=nl-amsxx-xxx` or `SNMP_WORKER;ip=10.0.0.1,oid=SNMPv2-MIB::sysName`

The key contains two parts: {STAT_PREFIX};list=of,labels=separated,by=coma

"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

from aka_stats.async_stats import available_stats, fetch_stats
from aka_stats.settings import config
from aka_stats.stats import STAT_NAMES


def escape_value(value):
    if value is None:
        return ""

    return str(value).replace("\\", "\\\\").replace("\n", "\\\n").replace('"', '\\"')


def dict_to_labels(labels: Dict[str, str]) -> str:
    """Convert dict to prometheus labels."""
    if not labels:
        return ""
    return "{" + ",".join([f'{label}="{escape_value(value)}"' for label, value in labels.items()]) + "}"


def generate_metrics(
    labels: Dict[str, str],
    stat: Dict[str, Any],
    prefix: str = config.namespace,
    fields: Optional[List[str]] = None,
):

    for stat_k, value in stat.items():
        if fields and stat_k not in fields:
            continue
        if stat_k == "last_time":
            # this is just a timestamp, we do not want to expose it to prometheus
            continue

        yield f"{prefix}_{stat_k.upper()}{dict_to_labels(labels)} {value}"


prometheus_stat_formatters = {}


def stat_formatter(stat_prefix):
    """
    Adds stat formatter. Formatters are needed to format the data for prometheus.

    ```python
    @stat_formatter("stat_prefix:")
    def formatter(key: str, stat: Dict[str, Any]):

        _, id_ = key.split(":",)
        return generate_metrics({"host_id": id_}, stat, f"MY_STAT_", ["count"])
    ```

    """

    def decorator(func):
        prometheus_stat_formatters[stat_prefix] = func
        return func

    return decorator


default_stat_formatter = stat_formatter(None)


@stat_formatter("errors__")
def error_stat(key: str, stat: Dict[str, Any]) -> Iterator[str]:
    _, *key_labels = key.split("__")

    labels_from_key: Dict[str, str]

    try:
        labels_from_key = dict(kl.split(":", 1) for kl in key_labels)
    except ValueError:
        labels_from_key = {"error": key_labels[-1]}

    return generate_metrics(labels_from_key, stat, f"{config.namespace.upper()}_ERROR", ["count"])


def parse_line_protocol_stat_key(key: str) -> Tuple[str, Dict[str, str]]:
    """Parseline protocolish key to stat prefix and key.

    Examples:
        SNMP_WORKER;hostname=abc.com,worker=snmp-mti
        will become:
        ("SNMP_WORKER", {"hostname": "abc.com", "worker": "snmp-mti"})


    """
    try:
        prefix, raw_labels = key.split(";", 1)
        labels = dict(raw_label.split("=", 1) for raw_label in raw_labels.split(","))
        return prefix, labels
    except ValueError:
        return key, {}


@default_stat_formatter
def line_protocol_label_formatter(key: str, stat: Dict[str, Any]) -> Iterator[str]:
    """Default formatter for stats."""
    prefix, labels = parse_line_protocol_stat_key(key)

    return generate_metrics(labels, stat, prefix, STAT_NAMES)


def parse_stat_to_prometheus(key: str, stat: Dict[str, Any]) -> Iterator[str]:

    for key_prefix, formatter in prometheus_stat_formatters.items():
        if key_prefix is not None and key.startswith(key_prefix):
            return formatter(key, stat)

    return prometheus_stat_formatters[None](key, stat)


async def prometheus_export(matcher: str = "*") -> AsyncIterator[str]:
    """Export to prometheus format."""
    async for stat_key in available_stats(matcher):
        stat_data = (await fetch_stats(stat_key))._asdict()
        for stat in parse_stat_to_prometheus(stat_key, stat_data):
            if stat:
                yield stat + "\n"
