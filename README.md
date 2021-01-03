# Aka Stats

Aka (赤 - red in japanese) Stats.

Unified module for keeping stats in Redis.

The goal is to have an easy way to measure an application, and then expose these metrics through an HTTP API,
either to process it in some web ui, or expose it to Prometheus.

```python
from aka_stats import Stats, timer

with Stats() as stats:

    t = timer()
    ...

    stats("task_done", next(t).stat)

```

Or for asynchronouse code:

```python
from aka_stats import Stats, timer

async def process_device(device_id: str):

    async with Stats() as stat:
        t = timer()
        ...
        stats("task_done", next(t).stat, extra_labels={"device_id": device_id})
```


## Installation

And add this package to your project:

```bash
poetry add aka-stats
```

## Usage Guide

Check out the usage guide here: [Usage.md](Usage.md)

## Prometheus formatters

Information how to write a formatter is here: [PrometheusFormatters.md](PrometheusFormatters.md)

## Optional Standalone HTTP API

Check out this guide here: [Included HTTP API](<Included HTTP API.md>)
