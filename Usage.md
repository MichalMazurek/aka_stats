# Using the Aka Stats

This document contains information about:

- How to connect redis to stats.
- How to add a single stat.
- How to add multiple stats.
- How stats are being calculated.
- Integration with FastAPI for basic endpoints
- Configuration through Environment Path


* [Setting up the Redis](#setting-up-the-redis)
  * [Reusing already existing redis connection](#reusing-already-existing-redis-connection)
    * [Asynchronous example for FastAPI](#asynchronous-example-for-fastapi)
    * [Synchronous example for a script](#synchronous-example-for-a-script)
  * [Using Aka Stats for Redis connections](#using-aka-stats-for-redis-connections)
    * [FastAPI example](#fastapi-example)
    * [Synchronous example](#synchronous-example)
* [Adding Single Stat](#adding-single-stat)
* [Adding multiple stats](#adding-multiple-stats)
* [Contexts](#contexts)
  * [Important things about contexts](#important-things-about-contexts)
    * [Context are stored in Redis - so in the memory](#context-are-stored-in-redis---so-in-the-memory)
    * [Context are hashed to md5 and stored in separate keys](#context-are-hashed-to-md5-and-stored-in-separate-keys)
* [Exception Handling](#exception-handling)
  * [Handling exceptions yourself](#handling-exceptions-yourself)
  * [Retrieving errors](#retrieving-errors)
* [Stats Calculation](#stats-calculation)
  * [Available stats](#available-stats)
  * [Redis Keys](#redis-keys)
* [FastAPI integration](#fastapi-integration)
  * [Attaching the endpoints](#attaching-the-endpoints)
  * [Endpoint: `/api/v1/available-stats`](#endpoint:-`/api/v1/available-stats`)
    * [Matching errors](#matching-errors)
  * [Endpoint: `/api/v1/stats/{label}`](#endpoint:-`/api/v1/stats/{label}`)
  * [Endpoint: `/api/v1/stats`](#endpoint:-`/api/v1/stats`)
  * [Endpoint: `/api/v1/stats-history/{label}`](#endpoint:-`/api/v1/stats-history/{label}`)
  * [Endpoint: `/api/v1/stat-contexts`](#endpoint:-`/api/v1/stat-contexts`)
* [Configuration through environment variables](#configuration-through-environment-variables)


## Setting up the Redis

Stats module already supports connecting to redis via `aioredis` and `redis`.

`Aioredis` is used for FastAPI endpoints for reporting stats and/or presenting them. `Redis` module is for adding stats in synchronous code.

### Reusing already existing redis connection

To reuse the already existing connection I need to attach it to objects in `aka_stats.redis`.

#### Asynchronous example for FastAPI

```python
from fastapi import FastAPI
from aioredis import create_redis_pool
from aka_stats.redis import async_redis

app = FastAPI()

@app.on_event("startup")
def connect_redis():

    redis = await create_redis_pool("redis://127.0.0.1:6379")
    # I'm attaching here reader and writer connection
    async_redis.attach(redis, redis)


@app.get("/api/v1/endpoint")
async def endpoint() -> str:

    async with async_redis as (reader, writer):
        return (await reader.get("key")).decode("utf8")
```

I can freely use the Redis interface from `aka_stats.redis` in my project, but I don't have to.

#### Synchronous example for a script

```python
from redis import Redis
from aka_stats.redis import sync_redis

redis = Redis.from_url("redis://127.0.0.1:6379")

# I'm attaching here read and writer
sync_redis.attach(redis, redis)
```

### Using Aka Stats for Redis connections

I can also use underlying redis capabilities of Aka Stats. To configure Redis connection I need to set an environmental var `AKA_STATS_REDIS_URL` to `redis://$YOURREDISHOST:6379`

#### FastAPI example

```python
from fastapi import FastAPI
from aka_stats.redis import async_redis

app = FastAPI()


@app.on_event("startup")
async def connect_redis():
    await async_redis.open_connection()


@app.on_event("shutdown")
async def close_redis():
    await async_redis.close()


@app.get("/api/v1/endpoint")
async def endpoint() -> str:

    async with async_redis() as (reader, _):
        return (await reader.get("endpoint_key")).decode("utf8")

```

Here I am using `open_connection` method to open the connection on app start. Why not using context manager? Because on each context exit there is a counter `async_redis.call_count` which will be decreased and when it will reach `0` then the connection to Redis will be closed. When I do `open_connection` I increase this count by `1` and this will protect the connection of being closed when I use `async_redis` somewhere else.

#### Synchronous example

As above, I need to pass redis url over `AKA_STATS_REDIS_URL` env var.

```python
from aka_stats.redis import sync_redis


with sync_redis() as (reader, writer):

    writer.set("endpoint_key", "something")
    if b"something" == reader.get("endpoint_key"):
        print("Data written.")
    else:
        print("Failed data write.")
```

This will automatically close the connection when the context will closed. If I don't want that, then I need to open connection using `open_connection`.

```python
from aka_stats.redis import sync_redis

sync_redis.open_connection()

with sync_redis() as (reader, writer):

    writer.set("endpoint_key", "something")
    if b"something" == reader.get("endpoint_key"):
        print("Data written.")
    else:
        print("Failed data write.")

with sync_redis() as (reader, writer):

    writer.set("endpoint_key", "something")
    if b"something" == reader.get("endpoint_key"):
        print("Data written.")
    else:
        print("Failed data write.")

sync_redis.close()

```

## Adding Single Stat

I want sometimes to add a single stat, for example, at the end of a longer process. This code assumes that there is `AKA_STATS_REDIS_URL` present in the environment if I don't want to use the default `redis://localhost:6379`

```python
from aka_stats import push_stat
from time import time

start_time = time()
file_path = Path("large_file.csv")

with file_path.open("r") as csv_io:

    for line_no, line in enumerate(csv_io):
        pass

    print(f"This file had {line_no+1} lines")

read_time = time() - start_time

# this will write directly to redis at this point
push_stat(f"file:{file_path.name}", read_time)

```

For asynchronous code I can use `push_stat_async`.

## Adding multiple stats

To add multiple stats I do not want to worry that I might loose stats due to an exception or that they are slowing my code. So I use `Stats` context manager.

```python
from aka_stats import Stats, timer
from pathlib import Path
import requests

urls = [...] # list of urls to download files from

with Stats() as stat:

    stat_gen = timer()
    for url in urls:
        response = requests.get(url)
        output = Path(url.replace("/", "-").replace(":", "-"))
        with output.open("w") as output_io:
            for chunk in response.iter_content(1024):
                output_io.write(chunk)
        timer_stat = next(stat_gen)
        stat(url, timer_stat.stat)

    stat("url-downloader", timer_stat.total)

print("All stats are written.")
```

When the `Stats` context exits, then all collected statistics are written to Redis.

For asynchronous code I can use this:

```python
import asyncio
from pathlib import Path
from aiofiles import open as a_open
from downloader import download
from aka_stats import Stats, timer


async def main(urls: List[str]):

    async with Stats() as stat:

        async def download_one(url: str):

            stat_timer = timer()
            response = await download(url)
            output = Path(url.replace("/", "-").replace(":", "-"))

            async with a_open(str(output), "wb") as output_io:
                async for chunk in response:
                    await output_io.write(chunk)

            stat(url, next(stat_timer).stat)


        stat_timer = timer()
        await asyncio.gather(*[download_one(url) for url in urls])
        stat("url-downloader", next(stat_timer).stat)

    print("All stats are written.")

urls = [...] # list of urls to download files from

asyncio.run(main(urls))

```

## Contexts

I use contexts to store information about stat itself.

```python
with Stats() as stat:
    for i in range(10):
        ...
        stat("stat_label", 1.4, context=b"the cake is a lie")
```

But there are couple important things to remember.

### Important things about contexts

#### Context are stored in Redis - so in the memory

I won't store lot of data there, and this data needs to be hashable to md5, so `context` is `str` or `bytes`.

#### Context are hashed to md5 and stored in separate keys

To not duplicate the data, context id is being calculated from the context using md5 and only it's id is stored in history key.

E.g. history key: `STATS::HISTORY::stat_label`

```redis
1587673195.4031308;3.5;06466bfef6e7e40e52d572902df6757d
1587673199.4031308;1.5;06466bfef6e7e40e52d572902df6757d
1587673139.4031308;1.2;06466bfef6e7e40e52d572902df6757d
```

And then you have a key `STATS::CONTEXTS::06466bfef6e7e40e52d572902df6757d` in redis:

```redis
GET STATS::CONTEXTS::06466bfef6e7e40e52d572902df6757d
b"the cake is a lie"
```

## Exception Handling

Within super powers of Stats object there is also handling of exception in your code, although it's only within the scope of the Stats context.

```python
with Stats() as stat:
    fail = int("test")
```

This will add two stats to Redis with labels

- `errors__all` – this keeps count of all the errors
- `errors__EXC:ValueError` – this keeps the counter for specific exception, and it will create a context with the traceback.

And the Traceback will be stored as a context.

### Handling exceptions yourself

I can provide the exception myself:

```python
with Stats() as stat:
    try:
        t = timer()
        # a job
        ...
        stat("stat_label", next(t).stat)
    except Exception as e:
        stat.exception(e)
```

Or I can allow `Stats` to do it by itself:

```python
with Stats() as stat:
    try:
        t = timer()
        # a job
        ...
        stat("stat_label", next(t).stat)
    except Exception:
        stat.exception()
```

I need to bare in mind that the `with` statement cannot be outside of any loop that runs forever, because then the stats will be written only on exit of that context manager.

### Retrieving errors

Below is the solution for getting the error stats, it is `async` code because it is currently used for FastAPI endpoints.

```python
In [1]: from aka_stats import Stats

In [2]: from aka_stats.async_stats import available_stats, fetch_stats, contexts

In [3]: async with Stats() as stat:  # generating exceptions
   ...:     t = int("test")
---------------------------------------------------------------------------
ValueError                                Traceback (most recent call last)
cell_name in async-def-wrapper()

ValueError: invalid literal for int() with base 10: 'test'

In [4]: keys = [k async for k in available_stats("errors__*")]; keys

In [5]: keys
Out[5]: ['errors__EXC:ValueError', 'errors__all']

In [6]: {key: await fetch_stats(key) for key in keys}
Out[6]:
{'errors__EXC:ValueError': Stats(max=1.0, total=1.0, count=1.0, stdev=0.0, avg=1.0, min=1.0, last=1.0, last_time=1587675230.423907),
 'errors__all': Stats(max=1.0, total=1.0, count=1.0, stdev=0.0, avg=1.0, min=1.0, last=1.0, last_time=1587675230.424013)}


In [7]: await stat_history("errors__EXC:ValueError")
Out[7]:
[Stat(timestamp=1587675742.972811, label='errors__EXC:ValueError', value=1.0, context_id='1473cb1a6f23e9a2263b3aae3821426e')]

In [8]: await contexts(["1473cb1a6f23e9a2263b3aae3821426e"])
Out[8]: {'1473cb1a6f23e9a2263b3aae3821426e': b'Traceback (most recent call last):\n  File "cell_name", line 5, in async-def-wrapper\nValueError: invalid literal for int() with base 10: \'test\'\n'}

```

## Stats Calculation

Storage that I use is Redis to ensure writing statistics from multiple sources in a short span of time. Redis makes sure that there is only one call done at the time, so I can't do the calculations in Python. All the calculations needs to be done on Redis side. Although Redis does not have any statistics capabilities it does support running scripts written in LUA.

### Available stats

For each stat label we calculate:

- Average
- Max
- Min
- Standard deviation
- Total

Also we keep

- Last value
- Last timestamp
- Count
- History specified by `AKA_STATS_HISTORY_SIZE`, default in `aka_stats.config`

### Redis Keys

I create Redis keys for each label, using prefix from `AKA_STATS_DEFAULT_PREFIX`.

So with defaults redis keys look like this:

- `AKA-STATS::LAST::{label}` - float
- `AKA-STATS::LAST_TIME::{label}` - float
- `AKA-STATS::MIN::{label}` - float
- `AKA-STATS::MAX::{label}` - float
- `AKA-STATS::AVG::{label}` - float
- `AKA-STATS::STDEV::{label}` - float
- `AKA-STATS::COUNT::{label}` - float
- `AKA-STATS::TOTAL::{label}` - float
- `AKA-STATS::TOTAL_SQ::{label}` - float (for stdev calculations)
- `AKA-STATS::HISTORY::{label}` - list of `timestamp;value;context_id`, limited by `AKA_STATS_HISTORY_SIZE`

Also there is a key storing contexts:

- `AKA-STATS::CONTEXTS::{context_id}` - bytes

All these keys expire after two weeks of last report. So if you are constantly adding stats for a year, you will keep the stats for one year, if you will have a break for two weeks then they will expire, and nothing will be in Redis.

## FastAPI integration

To enable stats endpoints in my FastAPI application I can attach some premade FastAPI endpoints.

These are the current available enpoints:

- `GET /api/v1/available-stats`
- `POST /api/v1/stats`
- `GET /api/v1/stats/{label}`
- `GET /api/v1/stats-history/{label}`
- `POST /api/v1/stat-contexts`

### Attaching the endpoints

```python
from fastapi import FastAPI
from aka_stats.api import app as stats_app


app = FastAPI()
stats_app.attach_routes(app)

```

Using above code I enable the stats endpoints in my app.

### Endpoint: `/api/v1/available-stats`

This endpoint takes one query parameter called `matcher`, so I can filter the stats labels like this:

`GET http://localhost:8000/api/v1/available-stats?matcher=DEVICE%3A%2A`

```json
["DEVICE::172.26.185.3", "DEVICE::172.27.217.56", "DEVICE::172.27.217.55"]
```

Which is actually matching `DEVICE::*`, I use [Redis SCAN](https://redis.io/commands/scan) command for looking through all the keys, so the matcher is using directly, more about matching in [Redis KEYS](https://redis.io/commands/keys).

Above matcher will try to match keys `AKA-STATS::HISTORY::{matcher}`.

#### Matching errors

Use matcher `error__*` to get all error stats.

### Endpoint: `/api/v1/stats/{label}`

This endpoint returns stats for a label.

`GET http://localhost:8000/api/v1/stats/url-downloader`

```json
{
  "avg": 40.351110649767,
  "count": 725.0,
  "last": 39.73086142539978,
  "last_time": 1586883727.65556,
  "max": 45.452062368393,
  "min": 38.798961877823,
  "stdev": 0.79583557884292,
  "total": 29254.55522108078
}
```

### Endpoint: `/api/v1/stats`

This endpoint returns stats for multiple labels passed in POST body in json list.

`POST http://localhost:8000/api/v1/stats ["url-downloader"]`

```json
{
  "url-downloader": {
    "avg": 40.351110649767,
    "count": 725.0,
    "last": 39.73086142539978,
    "last_time": 1586883727.65556,
    "max": 45.452062368393,
    "min": 38.798961877823,
    "stdev": 0.79583557884292,
    "total": 29254.55522108078
  }
}
```

### Endpoint: `/api/v1/stats-history/{label}`

This endpoint returns history for a label.

`GET http://localhost:8000/api/v1/stats-history/DEVICE::172.27.217.56`

```json
[
  {
    "label": "DEVICE::172.27.217.56",
    "timestamp": 1586884334.34567,
    "value": 39.564290046691895
  },
  {
    "label": "DEVICE::172.27.217.56",
    "timestamp": 1586883727.65556,
    "value": 39.73086142539978
  },
  {
    "label": "DEVICE::172.27.217.56",
    "timestamp": 1586883134.451101,
    "value": 39.6054949760437
  }
  ...
]
```

### Endpoint: `/api/v1/stat-contexts`

This endpoint returns contexts.


`POST http://localhost:8000/api/v1/stats ["1473cb1a6f23e9a2263b3aae3821426e"]`

```json
{
  "1473cb1a6f23e9a2263b3aae3821426e": "Traceback (most recent call last):\n  File \"cell_name\", line 5, in async-def-wrapper\nValueError: invalid literal for int() with base 10: 'test'\n"
}
```


## Configuration through environment variables

Each service that you run should have it's own redis namespace configured with `AKA_STATS_NAMESPACE`, to not
cross-contaminate services.

- `AKA_STATS_HISTORY_SIZE` - max number of stats kept in history, default: 1000
- `AKA_STATS_TIMEZONE` - timezone for timestamps with stats, default: Europe/Amsterdam
- `AKA_STATS_NAMESPACE` (previously: AKA_STATS_DEFAULT_PREFIX, will also work) - redis namespace for keys
- `AKA_STATS_REDIS_URL` - redis url, default: redis://localhost:6379

