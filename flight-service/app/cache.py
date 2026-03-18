import json
import logging
from datetime import datetime
from decimal import Decimal
from redis import Redis
from redis.sentinel import Sentinel
from app.config import settings

logger = logging.getLogger(__name__)


def build_redis_client() -> Redis:
    if settings.redis_mode.lower() == "sentinel":
        sentinel = Sentinel([(settings.redis_sentinel_host, settings.redis_sentinel_port)], socket_timeout=0.5)
        logger.info("using redis sentinel mode")
        return sentinel.master_for(settings.redis_sentinel_master, db=settings.redis_db, decode_responses=True)
    logger.info("using redis standalone mode")
    return Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db, decode_responses=True)


redis_client = build_redis_client()


def serialize_flight(data: dict) -> str:
    payload = dict(data)
    for key in ("departure_time", "arrival_time", "created_at", "updated_at"):
        if isinstance(payload.get(key), datetime):
            payload[key] = payload[key].isoformat()
    if isinstance(payload.get("price"), Decimal):
        payload["price"] = float(payload["price"])
    return json.dumps(payload)


def deserialize_flight(value: str) -> dict:
    payload = json.loads(value)
    for key in ("departure_time", "arrival_time", "created_at", "updated_at"):
        if payload.get(key):
            payload[key] = datetime.fromisoformat(payload[key])
    return payload


def get_json(key: str):
    value = redis_client.get(key)
    if value is None:
        logger.info("cache miss key=%s", key)
        return None
    logger.info("cache hit key=%s", key)
    return json.loads(value)


def set_json(key: str, value) -> None:
    redis_client.setex(key, settings.redis_ttl_seconds, json.dumps(value))


def delete_key(key: str) -> None:
    redis_client.delete(key)


def clear_search_cache() -> None:
    for key in redis_client.scan_iter("search:*"):
        redis_client.delete(key)
