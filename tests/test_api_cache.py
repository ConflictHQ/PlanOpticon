"""Tests for API response cache."""

import time

from video_processor.utils.api_cache import ApiCache


class TestApiCache:
    def test_set_and_get(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        cache.set("key1", {"data": "value"})
        result = cache.get("key1")
        assert result == {"data": "value"}

    def test_get_missing_key(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test", ttl=0)
        cache.set("key1", "value")
        # With TTL=0, any subsequent access should be expired
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_invalidate(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        cache.set("key1", "value")
        assert cache.get("key1") == "value"
        result = cache.invalidate("key1")
        assert result is True
        assert cache.get("key1") is None

    def test_invalidate_missing(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_clear_all(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        count = cache.clear()
        assert count == 3
        assert cache.get("a") is None

    def test_clear_older_than(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        cache.set("old", "value")
        # Setting older_than to a very large number means nothing gets cleared
        count = cache.clear(older_than=99999)
        assert count == 0

    def test_get_stats(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        cache.set("x", {"hello": "world"})
        cache.set("y", [1, 2, 3])
        stats = cache.get_stats()
        assert stats["namespace"] == "test"
        assert stats["entry_count"] == 2
        assert stats["total_size_bytes"] > 0

    def test_namespace_isolation(self, tmp_path):
        cache_a = ApiCache(tmp_path, namespace="ns_a")
        cache_b = ApiCache(tmp_path, namespace="ns_b")
        cache_a.set("key", "value_a")
        cache_b.set("key", "value_b")
        assert cache_a.get("key") == "value_a"
        assert cache_b.get("key") == "value_b"

    def test_creates_namespace_dir(self, tmp_path):
        ApiCache(tmp_path / "sub", namespace="deep")
        assert (tmp_path / "sub" / "deep").exists()

    def test_cache_path_uses_hash(self, tmp_path):
        cache = ApiCache(tmp_path, namespace="test")
        path = cache.get_cache_path("my_key")
        assert path.suffix == ".json"
        assert path.parent.name == "test"
