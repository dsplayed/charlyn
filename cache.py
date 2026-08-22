"""Simple TTL cache for tool results — reduces redundant API calls."""
import json
import time
from functools import wraps

CACHE: dict[str, dict] = {}
DEFAULT_TTL = 300  # 5 minutes


def _key(func_name: str, args: tuple, kwargs: dict) -> str:
    return f"{func_name}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"


def get(key: str):
    entry = CACHE.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["value"]
    if entry:
        del CACHE[key]
    return None


def put(key: str, value: str, ttl: int = DEFAULT_TTL):
    CACHE[key] = {"value": value, "expires": time.time() + ttl}


def cached(ttl: int = DEFAULT_TTL):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _key(func.__name__, args, kwargs)
            hit = get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            put(key, result, ttl)
            return result
        return wrapper
    return decorator


def clear():
    CACHE.clear()


def stats() -> str:
    return f"Cache: {len(CACHE)} entries"
