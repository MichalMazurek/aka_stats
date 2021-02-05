# Aka Stats

[![GitHub license](https://img.shields.io/github/license/MichalMazurek/aka_stats)](https://github.com/MichalMazurek/aka_stats/blob/main/LICENSE)
[![Test/Lint](https://img.shields.io/github/workflow/status/MichalMazurek/aka_stats/Test%20code/main)](https://github.com/MichalMazurek/aka_stats/actions?query=workflow%3A%22Test+code%22)
[![PyPI](https://img.shields.io/pypi/v/aka_stats)](https://pypi.org/project/aka-stats/)

Aka (赤 - red in japanese) Stats.

Unified module for keeping stats in Redis.

The goal is to have an easy way to measure an application, and then expose these metrics through a HTTP API,
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

Information how to write a formatter is here: [PrometheusFormatter.md](PrometheusFormatter.md)

## Optional Standalone HTTP API

Check out this guide here: [Included HTTP API](<Included http api.md>)

## Pytest plugin

This module is also a pytest plugin, providing a fixture `mock_stats` which collects stats instead of writing them
to Redis.

```python

def test_something(mock_stats):
    do_something()
    assert mock_stats[0] == (1612550961, "test", 1, None)

```

And the module with function:

```python

def do_something():
    with Stats() as stats:
        stat("test", 1)
```
