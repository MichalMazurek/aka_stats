import logging
import warnings

try:
    from fastapi import FastAPI
    from aka_stats.redis import async_redis
    from aka_stats.settings import config
    from aka_stats.api import app as stats_app

    app = stats_app.attach_routes(FastAPI(title="Aka Stats"))

    @app.on_event("startup")
    async def on_start():
        logging.basicConfig(format="[%(asctime)s] %(levelname)s - %(message)s", level=logging.INFO)
        log = logging.getLogger()
        log.info("Configuration options: ")
        [log.info(f"    {line}") for line in str(config).splitlines()]

        await async_redis.open_connection()

    @app.on_event("shutdown")
    async def on_shutdown():
        await async_redis.close()


except ImportError:
    warnings.warn("FastAPI not installed.")
