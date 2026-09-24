from redis import Redis
from rq import Queue

from .settings import settings

_redis = Redis.from_url(settings.redis_url)

# One queue per concern so a slow metrics pull never blocks a publish.
publish_q = Queue("publish", connection=_redis)
generate_q = Queue("generate", connection=_redis)
metrics_q = Queue("metrics", connection=_redis)
default_q = Queue("default", connection=_redis)


def redis() -> Redis:
    return _redis
