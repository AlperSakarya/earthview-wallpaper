"""
Source Registry - discovers, loads, and manages wallpaper source plugins.
"""

import importlib
import json
import pkgutil
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import WallpaperSource, ImageResult, ImageCategory

try:
    from logsetup import get_logger
    log = get_logger("registry")
except ImportError:  # standalone use without the app package
    import logging
    log = logging.getLogger("earthview.registry")


# How long (in seconds) before an image URL can be reused (7 days)
DEDUP_WINDOW = 7 * 24 * 3600


class RecentTracker:
    """
    Tracks recently used image URLs to prevent repeats.
    
    Stores URLs with timestamps. Any URL used within the dedup window
    is rejected, forcing the system to find a fresh image.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self._state_file = state_file or (
            Path.home() / ".config" / "earthview" / "recent_urls.json"
        )
        self._recent: Dict[str, float] = {}  # url -> timestamp
        self._load()

    def _load(self):
        """Load recent URLs from disk."""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r') as f:
                    self._recent = json.load(f)
                # Prune expired entries on load
                self._prune()
        except (json.JSONDecodeError, IOError):
            self._recent = {}

    def _save(self):
        """Persist recent URLs to disk."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, 'w') as f:
                json.dump(self._recent, f)
        except IOError:
            pass

    def _prune(self):
        """Remove entries older than the dedup window."""
        now = time.time()
        self._recent = {
            url: ts for url, ts in self._recent.items()
            if now - ts < DEDUP_WINDOW
        }

    def is_recent(self, url: str) -> bool:
        """Check if a URL was used recently (within dedup window)."""
        if url not in self._recent:
            return False
        age = time.time() - self._recent[url]
        return age < DEDUP_WINDOW

    def mark_used(self, url: str):
        """Mark a URL as recently used."""
        self._recent[url] = time.time()
        self._prune()
        self._save()

    @property
    def count(self) -> int:
        """Number of URLs in the recent tracker."""
        return len(self._recent)

    def clear(self):
        """Clear all tracked URLs."""
        self._recent = {}
        self._save()


class SourceRegistry:
    """
    Registry that auto-discovers and manages wallpaper sources.
    
    Uses round-robin source cycling to ensure ALL sources get used equally,
    and deduplicates URLs so no image repeats within 7 days.
    
    Usage:
        registry = SourceRegistry()
        registry.discover_sources()
        
        # Get a random image from any active source
        image = registry.fetch_random()
        
        # Get from a specific source
        image = registry.fetch_from("nasa_epic")
        
        # Get live satellite imagery
        image = registry.fetch_latest()
    """

    def __init__(self):
        self._sources: Dict[str, WallpaperSource] = {}
        self._active_sources: List[str] = []
        self._configs: Dict[str, dict] = {}
        self._source_cycle_index: int = 0
        self._recent = RecentTracker()
        self._cycle_state_file = (
            Path.home() / ".config" / "earthview" / "source_cycle.json"
        )
        self._load_cycle_state()

    def _load_cycle_state(self):
        """Load the source cycle position from disk."""
        try:
            if self._cycle_state_file.exists():
                with open(self._cycle_state_file, 'r') as f:
                    data = json.load(f)
                self._source_cycle_index = data.get("index", 0)
        except (json.JSONDecodeError, IOError):
            pass

    def _save_cycle_state(self):
        """Save the source cycle position."""
        try:
            self._cycle_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cycle_state_file, 'w') as f:
                json.dump({"index": self._source_cycle_index}, f)
        except IOError:
            pass

    def discover_sources(self) -> None:
        """Auto-discover all source plugins in the sources/ directory."""
        sources_dir = Path(__file__).parent
        
        for _, module_name, _ in pkgutil.iter_modules([str(sources_dir)]):
            if module_name in ('__init__', 'base', 'registry'):
                continue
            try:
                module = importlib.import_module(f'.{module_name}', package='sources')
                # Look for a class that subclasses WallpaperSource
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, WallpaperSource) and 
                        attr is not WallpaperSource):
                        source = attr()
                        if source.source_id in self._configs:
                            source.configure(self._configs[source.source_id])
                        self._sources[source.source_id] = source
            except Exception as e:
                log.warning("failed to load source %s: %s", module_name, e)

    def register_source(self, source: WallpaperSource) -> None:
        """Manually register a source instance."""
        if source.source_id in self._configs:
            source.configure(self._configs[source.source_id])
        self._sources[source.source_id] = source

    def set_config(self, source_id: str, config: dict) -> None:
        """Set configuration for a source."""
        self._configs[source_id] = config
        if source_id in self._sources:
            self._sources[source_id].configure(config)

    def set_active_sources(self, source_ids: List[str]) -> None:
        """Set which sources are active. Empty list means all."""
        self._active_sources = source_ids

    @property
    def all_sources(self) -> Dict[str, WallpaperSource]:
        """All registered sources."""
        return self._sources.copy()

    @property
    def active_sources(self) -> Dict[str, WallpaperSource]:
        """Currently active sources (all if none specifically set)."""
        if not self._active_sources:
            return {sid: s for sid, s in self._sources.items() if s.is_available()}
        return {sid: self._sources[sid] for sid in self._active_sources
                if sid in self._sources and self._sources[sid].is_available()}

    @property
    def live_sources(self) -> Dict[str, WallpaperSource]:
        """Sources that support real-time imagery."""
        return {sid: s for sid, s in self.active_sources.items() if s.supports_live}

    @property
    def location_sources(self) -> Dict[str, WallpaperSource]:
        """Sources that support location-based fetching."""
        return {sid: s for sid, s in self.active_sources.items() if s.supports_location}

    def get_source(self, source_id: str) -> Optional[WallpaperSource]:
        """Get a specific source by ID."""
        return self._sources.get(source_id)

    def _get_next_source(self) -> Optional[WallpaperSource]:
        """
        Get the next source in the round-robin cycle.
        Ensures every source gets used before any repeats.
        """
        sources = list(self.active_sources.values())
        if not sources:
            return None

        # Wrap index
        self._source_cycle_index = self._source_cycle_index % len(sources)
        source = sources[self._source_cycle_index]

        # Advance for next call
        self._source_cycle_index = (self._source_cycle_index + 1) % len(sources)
        self._save_cycle_state()

        return source

    def _fetch_unique_from_source(self, source: WallpaperSource,
                                   max_attempts: int = 10) -> Optional[ImageResult]:
        """
        Fetch from a source, rejecting any URL seen in the last 7 days.

        Retries only when the source returned a usable image that happened to
        be a duplicate. A None return means the source itself failed (network
        error, rate limit), so we stop immediately rather than burning API
        quota on retries that cannot succeed.
        """
        for _ in range(max_attempts):
            try:
                result = source.fetch_random()
            except Exception as e:
                log.warning("source %s raised: %s", source.source_id, e)
                return None
            if result is None:
                log.warning("source %s returned no image (failure or rate limit)",
                            source.source_id)
                return None
            if not self._recent.is_recent(result.url):
                log.debug("source %s produced fresh image: %s",
                          source.source_id, result.url)
                return result
            log.debug("source %s produced duplicate, retrying: %s",
                      source.source_id, result.url)
        log.info("source %s exhausted %d attempts without a fresh image",
                 source.source_id, max_attempts)
        return None

    def fetch_random(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch a unique random image using round-robin source cycling.
        
        - Cycles through sources in order (Earth View -> NASA EPIC -> GOES -> ...)
        - Never repeats the same image URL within 7 days
        - If the current source fails, tries the next sources
        
        Args:
            source_id: If specified, fetch only from this source.
        """
        if source_id:
            source = self._sources.get(source_id)
            if source and source.is_available():
                result = self._fetch_unique_from_source(source)
                if result:
                    self._recent.mark_used(result.url)
                    return result
            return None

        sources = list(self.active_sources.values())
        if not sources:
            return None

        # Try each source starting from current cycle position
        # This ensures we cycle through ALL sources
        num_sources = len(sources)
        start_index = self._source_cycle_index % num_sources

        for i in range(num_sources):
            idx = (start_index + i) % num_sources
            source = sources[idx]
            
            result = self._fetch_unique_from_source(source)
            if result:
                # Advance cycle past this source
                self._source_cycle_index = (idx + 1) % num_sources
                self._save_cycle_state()
                self._recent.mark_used(result.url)
                return result

        # All sources failed to produce a unique image - 
        # this should be extremely rare. Allow a repeat as last resort.
        source = sources[start_index % num_sources]
        try:
            result = source.fetch_random()
            if result:
                self._source_cycle_index = (start_index + 1) % num_sources
                self._save_cycle_state()
                self._recent.mark_used(result.url)
                return result
        except Exception:
            pass

        return None

    def fetch_latest(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch the latest live image."""
        if source_id:
            source = self._sources.get(source_id)
            if source and source.supports_live:
                result = source.fetch_latest()
                if result:
                    self._recent.mark_used(result.url)
                return result
            return None

        sources = list(self.live_sources.values())
        if not sources:
            return None

        random.shuffle(sources)
        for source in sources:
            try:
                result = source.fetch_latest()
                if result:
                    self._recent.mark_used(result.url)
                    return result
            except Exception:
                continue

        return None

    def fetch_by_category(self, category: ImageCategory,
                          source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch an image matching a time category."""
        if source_id:
            source = self._sources.get(source_id)
            if source:
                result = source.fetch_by_category(category)
                if result and not self._recent.is_recent(result.url):
                    self._recent.mark_used(result.url)
                    return result
            return None

        # Use round-robin but with category filter
        sources = list(self.active_sources.values())
        if not sources:
            return self.fetch_random()

        num_sources = len(sources)
        start_index = self._source_cycle_index % num_sources

        for i in range(num_sources):
            idx = (start_index + i) % num_sources
            source = sources[idx]
            
            for _ in range(5):  # Try a few times per source
                try:
                    result = source.fetch_by_category(category)
                    if result and not self._recent.is_recent(result.url):
                        self._source_cycle_index = (idx + 1) % num_sources
                        self._save_cycle_state()
                        self._recent.mark_used(result.url)
                        return result
                except Exception:
                    break

        # Fallback
        return self.fetch_random()

    def _fetch_unique_near_location(self, source: WallpaperSource,
                                    latitude: float, longitude: float,
                                    radius_km: float,
                                    max_attempts: int = 15) -> Optional[ImageResult]:
        """
        Fetch geo-filtered imagery from a source, rejecting recent URLs.

        As with _fetch_unique_from_source, a None return ends the attempt
        immediately since it signals source failure rather than a duplicate.
        """
        for _ in range(max_attempts):
            try:
                result = source.fetch_near_location(latitude, longitude, radius_km)
            except Exception as e:
                log.warning("source %s geo lookup raised: %s", source.source_id, e)
                return None
            if result is None:
                log.warning("source %s geo lookup returned no image",
                            source.source_id)
                return None
            if not self._recent.is_recent(result.url):
                return result
            log.debug("source %s geo duplicate, retrying: %s",
                      source.source_id, result.url)
        return None

    def fetch_near_location(self, latitude: float, longitude: float,
                            radius_km: float = 500,
                            source_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch an image with location awareness, using ALL active sources.

        Location-capable sources (e.g. Earth View) return imagery near the
        given coordinates. Sources without geographic indexing (satellites,
        APOD, Unsplash) still participate via their normal random fetch, so
        location mode never collapses onto a single source.

        Uses the same round-robin cycle and 7-day dedup as fetch_random.
        """
        if source_id:
            source = self._sources.get(source_id)
            if not source:
                return None
            if source.supports_location:
                result = self._fetch_unique_near_location(
                    source, latitude, longitude, radius_km)
            else:
                result = self._fetch_unique_from_source(source)
            if result:
                self._recent.mark_used(result.url)
            return result

        sources = list(self.active_sources.values())
        if not sources:
            return None

        num_sources = len(sources)
        start_index = self._source_cycle_index % num_sources

        for i in range(num_sources):
            idx = (start_index + i) % num_sources
            source = sources[idx]

            if source.supports_location:
                result = self._fetch_unique_near_location(
                    source, latitude, longitude, radius_km)
            else:
                result = self._fetch_unique_from_source(source)

            if result:
                self._source_cycle_index = (idx + 1) % num_sources
                self._save_cycle_state()
                self._recent.mark_used(result.url)
                return result

        # Nothing unique anywhere - fall back to normal rotation
        return self.fetch_random()
