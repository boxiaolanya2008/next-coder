# Shared in-memory cache for read-only tools.
# write_file and edit_file clear entries that match their file path.

_cache = {}


def tcache_get(key):
    # get a cached value, returns None if missing
    return _cache.get(key)


def tcache_set(key, value):
    # store a value in the cache
    _cache[key] = value


def tcache_clear(path_filter=None):
    # clear all cache, or only entries containing path_filter
    global _cache
    if path_filter is None:
        _cache.clear()
    else:
        _cache = {k: v for k, v in _cache.items() if path_filter not in k}
