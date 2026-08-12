"""
NASA Astronomy Picture of the Day (APOD) source plugin.

Provides daily stunning images of space, Earth, and astronomy.
Uses the free NASA APOD API with a demo key (limited rate) or user-provided key.

API: https://api.nasa.gov/planetary/apod
"""

import random
import requests
from typing import Optional
from datetime import datetime, timedelta

from .base import WallpaperSource, ImageResult, ImageCategory

try:
    from logsetup import get_logger
    log = get_logger("nasa_apod")
except ImportError:  # standalone use without the app package
    import logging
    log = logging.getLogger("earthview.nasa_apod")



class NasaApodSource(WallpaperSource):
    """
    NASA APOD - Astronomy Picture of the Day.
    
    Daily curated images of space, nebulae, galaxies, and Earth from space.
    Works with the free DEMO_KEY (30 requests/hour) or a personal API key.
    """

    API_URL = "https://api.nasa.gov/planetary/apod"
    DEFAULT_KEY = "DEMO_KEY"

    def __init__(self):
        self._api_key = self.DEFAULT_KEY

    @property
    def name(self) -> str:
        return "NASA APOD"

    @property
    def source_id(self) -> str:
        return "nasa_apod"

    @property
    def description(self) -> str:
        return "Daily astronomy and Earth-from-space images curated by NASA scientists"

    @property
    def requires_api_key(self) -> bool:
        # Works with DEMO_KEY but rate-limited
        return False

    @property
    def supports_live(self) -> bool:
        return True  # Has daily updates

    def configure(self, config: dict) -> None:
        """Accept optional API key configuration."""
        if "api_key" in config:
            self._api_key = config["api_key"]

    def _fetch_apod(self, date: Optional[str] = None, count: Optional[int] = None) -> list:
        """Fetch APOD data from NASA API."""
        params = {"api_key": self._api_key}
        if date:
            params["date"] = date
        if count:
            params["count"] = count
            
        try:
            response = requests.get(self.API_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            # Single result comes as dict, multiple as list
            if isinstance(data, dict):
                return [data]
            return data
        except Exception as e:
            log.warning("nasa_apod api error: %s", e)
            return []

    def _parse_entry(self, entry: dict) -> Optional[ImageResult]:
        """Convert APOD API response to ImageResult."""
        # Skip videos - only use images
        media_type = entry.get("media_type", "image")
        if media_type != "image":
            return None

        # Prefer HD URL
        url = entry.get("hdurl", entry.get("url", ""))
        if not url:
            return None

        title = entry.get("title", "NASA APOD")
        explanation = entry.get("explanation", "")
        date = entry.get("date", "")
        
        # Truncate explanation for description
        desc = explanation[:200] + "..." if len(explanation) > 200 else explanation

        return ImageResult(
            url=url,
            source_name=self.name,
            title=f"APOD: {title}",
            description=desc,
            category=ImageCategory.NIGHT,  # Space images suit night theme
            tags=["space", "astronomy", "nasa", "apod"],
            source_id=date,
            attribution=f"NASA APOD - {entry.get('copyright', 'Public Domain')}",
        )

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random APOD image."""
        # Use count parameter for random selection
        entries = self._fetch_apod(count=5)
        
        # Filter to only images (skip videos)
        for entry in entries:
            result = self._parse_entry(entry)
            if result:
                return result

        # Fallback: try random dates
        for _ in range(3):
            days_ago = random.randint(1, 3000)  # ~8 years of archives
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            entries = self._fetch_apod(date=date)
            if entries:
                result = self._parse_entry(entries[0])
                if result:
                    return result

        return None

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch today's APOD."""
        entries = self._fetch_apod()
        if entries:
            result = self._parse_entry(entries[0])
            if result:
                return result
            
        # Today might be a video, try yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        entries = self._fetch_apod(date=yesterday)
        if entries:
            return self._parse_entry(entries[0])
        
        return None
