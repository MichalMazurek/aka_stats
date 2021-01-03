from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Optional, Tuple

from aioredis import Redis as AioRedis, create_redis_pool
from redis import BlockingConnectionPool, ConnectionPool
from redis.client import Redis

from aka_stats.settings import config


class SyncRedis(AbstractContextManager):

    reader: Optional[Redis]
    writer: Optional[Redis]
    pool: Optional[ConnectionPool]

    def __init__(self):
        self.reader = None
        self.writer = None
        self.pool = None
        self.call_count = 0
        self.external_connection = False

    def __call__(self):
        return self

    def make_connection(self, redis_url: Optional[str] = None):
        the_redis_url = redis_url or config.redis_url
        pool = BlockingConnectionPool.from_url(the_redis_url)
        redis = Redis(connection_pool=pool)
        self.pool = pool
        return redis, redis

    def __enter__(self) -> Tuple[Redis, Redis]:
        if self.pool is None:
            self.reader, self.writer = self.make_connection()
        self.call_count += 1
        return self.reader, self.writer  # type: ignore

    def open_connection(self, redis_url: Optional[str] = None):
        self.reader, self.writer = self.make_connection(redis_url)
        self.call_count += 1
        return self.reader, self.writer

    def attach(self, reader: Redis, writer: Redis):
        self.reader = reader
        self.writer = writer
        self.external_connection = True

    def redis_pair(self):
        return self.__enter__()

    def __exit__(self, *exc):
        self.call_count -= 1
        if self.call_count <= 0:
            self.close()

    def close(self):
        if self.external_connection:
            return
        self.pool.disconnect()
        self.pool = None
        self.reader = None
        self.writer = None


sync_redis = SyncRedis()


class AsyncRedis(AbstractAsyncContextManager):
    def __init__(self):
        self.reader = None
        self.writer = None
        self.call_count = 0
        self.external_connection = False

    def __call__(self):
        return self

    async def __aenter__(self):
        if not self.reader:
            self.reader, self.writer = await self.make_connection()
        self.call_count += 1
        return self.reader, self.writer

    async def make_connection(self, redis_url: Optional[str] = None) -> Tuple[AioRedis, AioRedis]:
        the_redis_url = redis_url or config.redis_url
        redis = await create_redis_pool(the_redis_url)
        return redis, redis

    async def open_connection(self, redis_url: Optional[str] = None) -> Tuple[AioRedis, AioRedis]:
        self.reader, self.writer = await self.make_connection(redis_url)
        self.call_count += 1
        return self.reader, self.writer

    def attach(self, reader: AioRedis, writer: AioRedis):
        self.reader = reader
        self.writer = writer
        self.external_connection = True

    async def redis_pair(self):
        return await self.__aenter__()

    async def __aexit__(self, *exc):
        self.call_count -= 1
        if self.call_count <= 0:
            await self.close()

    async def close(self):
        if self.external_connection:
            return
        self.reader.close()
        await self.reader.wait_closed()
        self.reader = None
        self.writer = None


async_redis = AsyncRedis()
