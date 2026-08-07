"""
Source Registry - discovers, loads, and manages wallpaper source plugins.
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional

from .base import WallpaperSource, ImageResult, ImageCategory


class SourceRegistry:
    """
    Registry that auto-discovers and manages wallpaper sources.
    
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
                print(f"Warning: Failed to load source '{module_name}': {e}")

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

    def fetch_random(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch a random image from active sources.
        
        Args:
            source_id: If specified, fetch only from this source.
        """
        import random

        if source_id:
            source = self._sources.get(source_id)
            if source and source.is_available():
                return source.fetch_random()
            return None

        sources = list(self.active_sources.values())
        if not sources:
            return None

        # Weighted random - try each source until one succeeds
        random.shuffle(sources)
        for source in sources:
            try:
                result = source.fetch_random()
                if result:
                    return result
            except Exception as e:
                print(f"Source {source.name} failed: {e}")
                continue

        return None

    def fetch_latest(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch the latest live image."""
        import random

        if source_id:
            source = self._sources.get(source_id)
            if source and source.supports_live:
                return source.fetch_latest()
            return None

        sources = list(self.live_sources.values())
        if not sources:
            return None

        random.shuffle(sources)
        for source in sources:
            try:
                result = source.fetch_latest()
                if result:
                    return result
            except Exception:
                continue

        return None

    def fetch_by_category(self, category: ImageCategory,
                          source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch an image matching a time category."""
        import random

        if source_id:
            source = self._sources.get(source_id)
            if source:
                return source.fetch_by_category(category)
            return None

        sources = [s for s in self.active_sources.values() if s.supports_category]
        if not sources:
            # Fallback to any source
            return self.fetch_random()

        random.shuffle(sources)
        for source in sources:
            try:
                result = source.fetch_by_category(category)
                if result:
                    return result
            except Exception:
                continue

        return self.fetch_random()

    def fetch_near_location(self, latitude: float, longitude: float,
                            radius_km: float = 500,
                            source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch an image near a location."""
        import random

        if source_id:
            source = self._sources.get(source_id)
            if source and source.supports_location:
                return source.fetch_near_location(latitude, longitude, radius_km)
            return None

        sources = list(self.location_sources.values())
        if not sources:
            return self.fetch_random()

        random.shuffle(sources)
        for source in sources:
            try:
                result = source.fetch_near_location(latitude, longitude, radius_km)
                if result:
                    return result
            except Exception:
                continue

        return self.fetch_random()
