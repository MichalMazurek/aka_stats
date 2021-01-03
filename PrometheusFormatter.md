# Prometheus

[Prometheus](https://prometheus.io/) is a tool for collection and presentation of metrics. This documents tells about
how to export collected metrics to Prometheus.

* [Formatters](#formatters)
* [Simple example with default formatter](#simple-example-with-default-formatter)
* [Your own personal formatters](#your-own-personal-formatters)
* [Errors and Exceptions](#errors-and-exceptions)

## Formatters

As stats can use different stat labels, we need different formatters for the prometheus export.
According to [this document](https://github.com/Showmax/prometheus-docs/blob/master/content/docs/instrumenting/exposition_formats.md). Prometheus text file should look more something like this:

```text
# HELP http_requests_total The total number of HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="post",code="200"} 1027 1395066363000
http_requests_total{method="post",code="400"}    3 1395066363000
```

The format really is like this:

```text
metric_name [
  "{" label_name "=" `"` label_value `"` { "," label_name "=" `"` label_value `"` } [ "," ] "}"
] value [ timestamp ]
```

So in real life we export data like this through our API (`GET /api/v1/stats-prometheus`):

```
SNMP_WORKER_AVG{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.022757013638814
SNMP_WORKER_LAST{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.02188563346862793
SNMP_WORKER_TOTAL{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.13654208183288574
SNMP_WORKER_STDEV{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.010868633238619
SNMP_WORKER_MAX{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.04438591003418
SNMP_WORKER_MIN{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 0.015146017074585
SNMP_WORKER_COUNT{worker="snmp-mti",device="213.51.1.94",OID="SNMPv2-MIB::sysName"} 6.0
```

Above example is made from these keys:

```
SNMP::MAX::213.51.1.94__SNMPv2-MIB::sysName
SNMP::LAST_TIME::213.51.1.94__SNMPv2-MIB::sysName
SNMP::TOTAL_SQ::213.51.1.94__SNMPv2-MIB::sysName
SNMP::TOTAL::213.51.1.94__SNMPv2-MIB::sysName
SNMP::COUNT::213.51.1.94__SNMPv2-MIB::sysName
SNMP::MIN::213.51.1.94__SNMPv2-MIB::sysName
SNMP::LAST::213.51.1.94__SNMPv2-MIB::sysName
SNMP::HISTORY::213.51.1.94__SNMPv2-MIB::sysName
SNMP::STDEV::213.51.1.94__SNMPv2-MIB::sysName
SNMP::AVG::213.51.1.94__SNMPv2-MIB::sysName
```

## Simple example with default formatter

The simpliest example is when I use a main stat label and some extra labels for additional information.

```python
with Stats() as stat:
    do_something(host_id)
    stat("jobs", 1, extra_labels={"host": host_id})
```

Out of this example when I will export metrics to prometheus I will receive this:

```
jobs_AVG{host="10.0.0.01"} 1
jobs_LAST{host="10.0.0.01"} 1
jobs_TOTAL{host="10.0.0.01"} 1
# ... etc
```

Above is just a sample. To achieve that, the prometheus exportes uses the `default_formatter`.
Which looks like this:

```python

# aka_stats/prometheus.py

@default_stat_formatter
def line_protocol_label_formatter(key: str, stat: Dict[str, Any]) -> Iterator[str]:
    """Default formatter for stats."""
    prefix, labels = parse_line_protocol_stat_key(key)
    return generate_metrics(labels, stat, prefix, STAT_NAMES)
```

If I would like to change the `default_formatter` I can user `default_stat_formatter` decorator from
`aka_stats.prometheus` module.


## Your own personal formatters

So let's say I want to do some specific formatters and I am adding stats like this:

```python
with Stats() as stat:
    do_something(host_id)
    stat(f"stat:{host_id}", 1)
```

Which is just a simple counter that something happened.

```python
# this is a way to register formatter for the stat label prefix
@stat_formatter("stat:")
def simple_stat_formatter(key: str, stat_data: Dict[str, any]) -> Iterator[str]:
    _, host_id = key.split(":", 1)

    labels = {"host_id": host_id}
    return generate_metrics(labels, stat_data, "SIMPLE_STAT", fields=["count"])
```

Above example, will generate stats like this:

```
SIMPLE_STAT{host_id="1"} 1
```

If we are measuring time, we can add more fields. So for example our stat looks like this:

```python
with Stats() as stat:
    t = timer()
    do_something(host_id)
    measure = next(t)
    stat(f"timer:{host_id}", measure.stat)
```

With this we want the count of measures, average, last value, max, min and standard deviation.
So our formatter will look like this:

```python
@stat_formatter("timer:")
def simple_stat_formatter(key: str, stat_data: Dict[str, any]) -> Iterator[str]:
    _, host_id = key.split(":", 1)

    labels = {"host_id": host_id}
    return generate_metrics(labels, stat_data, "SIMPLE_STAT", fields=["count", "last", "min", "max", "stdev", "avg"])
```

Name of the fields are in `STAT_NAMES` in `aka_stats.stats`, module.

```python
STAT_NAMES = {"count", "avg", "stdev", "max", "min", "total", "last", "last_time"}
```

Remember that you can record as many stats as you like and also you can add as many formatters as you need.

## Errors and Exceptions

Recorded Exceptions are formatted using this formatter:

```python
# aka_stats/prometheus.py
@stat_formatter("errors__")
def error_stat(key: str, stat: Dict[str, Any]) -> Iterator[str]:
    _, *key_labels = key.split("__")
    try:
        labels_from_key = dict(cast(List[Tuple[str, str]], [kl.split(":", 1) for kl in key_labels]))
    except ValueError:
        labels_from_key = dict(("error", k) for k in key_labels)
    return generate_metrics(labels_from_key, stat, f"{config.namespace.upper()}_ERROR", ["count"])
```

So the stat label usually looks like this: `errors__Exception:KeyError__morelabels:values`.
But you do not have to worry about it, it's all included.

