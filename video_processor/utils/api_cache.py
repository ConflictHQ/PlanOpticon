"""Caching system for API responses to reduce API calls and costs."""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class ApiCache:
    """Disk-based API response cache."""

    def __init__(
        self,
        cache_dir: Union[str, Path],
        namespace: str = "default",
        ttl: int = 86400,  # 24 hours in seconds
    ):
        """
        Initialize API cache.

        Parameters
        ----------
        cache_dir : str or Path
            Directory for cache files
        namespace : str
            Cache namespace for organizing cache files
        ttl : int
            Time-to-live for cache entries in seconds
        """
        self.cache_dir = Path(cache_dir)
        self.namespace = namespace
        self.ttl = ttl

        # Ensure namespace directory exists
        self.namespace_dir = self.cache_dir / namespace
        self.namespace_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Initialized API cache in {self.namespace_dir}")

    def get_cache_path(self, key: str) -> Path:
        """
        Get path to cache file for key.

        Parameters
        ----------
        key : str
            Cache key

        Returns
        -------
        Path
            Path to cache file
        """
        # Hash the key to ensure valid filename
        hashed_key = hashlib.md5(key.encode()).hexdigest()
        return self.namespace_dir / f"{hashed_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Parameters
        ----------
        key : str
            Cache key

        Returns
        -------
        object or None
            Cached value if available and not expired, None otherwise
        """
        cache_path = self.get_cache_path(key)

        # Check if cache file exists
        if not cache_path.exists():
            return None

        try:
            # Read cache file
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check if cache entry is expired
            timestamp = cache_data.get("timestamp", 0)
            now = time.time()

            if now - timestamp > self.ttl:
                logger.debug(f"Cache entry expired for {key}")
                return None

            logger.debug(f"Cache hit for {key}")
            return cache_data.get("value")

        except Exception as e:
            logger.warning(f"Error reading cache: {str(e)}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Set value in cache.

        Parameters
        ----------
        key : str
            Cache key
        value : object
            Value to cache (must be JSON serializable)

        Returns
        -------
        bool
            True if successful, False otherwise
        """
        cache_path = self.get_cache_path(key)

        try:
            # Prepare cache data
            cache_data = {"timestamp": time.time(), "value": value}

            # Write to cache file
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False)

            logger.debug(f"Cached value for {key}")
            return True

        except Exception as e:
            logger.warning(f"Error writing to cache: {str(e)}")
            return False

    def invalidate(self, key: str) -> bool:
        """
        Invalidate cache entry.

        Parameters
        ----------
        key : str
            Cache key

        Returns
        -------
        bool
            True if entry was removed, False otherwise
        """
        cache_path = self.get_cache_path(key)

        if cache_path.exists():
            try:
                os.remove(cache_path)
                logger.debug(f"Invalidated cache for {key}")
                return True
            except Exception as e:
                logger.warning(f"Error invalidating cache: {str(e)}")

        return False

    def clear(self, older_than: Optional[int] = None) -> int:
        """
        Clear all cache entries or entries older than specified time.

        Parameters
        ----------
        older_than : int, optional
            Clear entries older than this many seconds

        Returns
        -------
        int
            Number of entries cleared
        """
        count = 0
        now = time.time()

        for cache_file in self.namespace_dir.glob("*.json"):
            try:
                # Check file age if criteria provided
                if older_than is not None:
                    file_age = now - os.path.getmtime(cache_file)
                    if file_age <= older_than:
                        continue

                # Remove file
                os.remove(cache_file)
                count += 1

            except Exception as e:
                logger.warning(f"Error clearing cache file {cache_file}: {str(e)}")

        logger.info(f"Cleared {count} cache entries from {self.namespace}")
        return count

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns
        -------
        dict
            Cache statistics
        """
        cache_files = list(self.namespace_dir.glob("*.json"))
        total_size = sum(os.path.getsize(f) for f in cache_files)

        # Analyze age distribution
        now = time.time()
        age_distribution = {"1h": 0, "6h": 0, "24h": 0, "older": 0}

        for cache_file in cache_files:
            file_age = now - os.path.getmtime(cache_file)

            if file_age <= 3600:  # 1 hour
                age_distribution["1h"] += 1
            elif file_age <= 21600:  # 6 hours
                age_distribution["6h"] += 1
            elif file_age <= 86400:  # 24 hours
                age_distribution["24h"] += 1
            else:
                age_distribution["older"] += 1

        return {
            "namespace": self.namespace,
            "entry_count": len(cache_files),
            "total_size_bytes": total_size,
            "age_distribution": age_distribution,
        }
