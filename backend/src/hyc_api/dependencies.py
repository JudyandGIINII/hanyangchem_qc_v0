from __future__ import annotations

from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from hyc_api.config import Settings


class ReadinessDependencies:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def database_ok(self) -> bool:
        if not self.settings.check_database_on_ready:
            return True
        engine: Engine | None = None
        try:
            engine = create_engine(self.settings.database_url, pool_pre_ping=True)
            with engine.connect() as connection:
                value = connection.execute(text("SELECT 1")).scalar_one()
                return isinstance(value, int) and value == 1
        except (OSError, SQLAlchemyError, ValueError):
            return False
        finally:
            if engine is not None:
                engine.dispose()

    def redis_ok(self) -> bool:
        if not self.settings.check_redis_on_ready:
            return True
        client: Redis | None = None
        try:
            client = Redis.from_url(
                self.settings.redis_url,
                socket_connect_timeout=self.settings.request_timeout_seconds,
            )
            return bool(client.ping())
        except (OSError, RedisError, ValueError):
            return False
        finally:
            if client is not None:
                client.close()


ReadinessFactory = Callable[[Settings], ReadinessDependencies]
