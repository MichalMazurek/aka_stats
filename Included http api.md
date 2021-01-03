# Using the http api included with Aka Stats

Optionally if your application does not have a HTTP API, because it's a script or scheduled service, you can use included FastAPI app to serve the stats API.

## Installing additional packages

To run the API you need two additional packages: `fastapi` which is the framework used by stats and `uvicorn` or `hypercorn` for running the HTTP server.

```bash
pip install fastapi uvicorn
```

## Running the API

To run the API you need then this command:

```bash
$ uvicorn aka_stats.app:app
INFO:     Started server process [81559]
INFO:     Waiting for application startup.
INFO:     Configuration options:
INFO:         AKA_STATS_TIMEZONE = Europe/London
INFO:         AKA_STATS_HISTORY_SIZE = 1000
INFO:         AKA_STATS_DEFAULT_PREFIX = AKA-STATS
INFO:         AKA_STATS_REDIS_URL = redis://127.0.0.1:6379
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

For hypercorn use this:

```bash
$ hypercorn aka_stats.app:app
[2020-05-07 16:36:50,787] INFO - Configuration options:
[2020-05-07 16:36:50,787] INFO -     AKA_STATS_REDIS_URL = redis://127.0.0.1:6379
[2020-05-07 16:36:50,787] INFO -     AKA_STATS_HISTORY_SIZE = 1000
[2020-05-07 16:36:50,788] INFO -     AKA_STATS_TIMEZONE = Europe/Amsterdam
[2020-05-07 16:36:50,788] INFO -     AKA_STATS_DEFAULT_PREFIX = AKA-STATS
Running on 127.0.0.1:8000 over http (CTRL + C to quit)
```

What's the difference? Hypercorn supports http2, but for that you need ssl certs.

## Configuring the API

If you are using additional prefixes, using different redis url than in the config, you can use environment variables to configure them:

```
AKA_STATS_TIMEZONE = Europe/Amsterdam
AKA_STATS_HISTORY_SIZE = 1000
AKA_STATS_DEFAULT_PREFIX = AKA-STATS
AKA_STATS_REDIS_URL = redis://127.0.0.1:6379
```
