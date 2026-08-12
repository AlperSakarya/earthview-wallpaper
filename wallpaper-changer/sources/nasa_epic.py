"""
NASA EPIC (Earth Polychromatic Imaging Camera) source plugin.

Provides real-time full-disc images of Earth taken from the DSCOVR satellite
at Lagrange Point 1 (about 1 million miles from Earth).

No API key required. Updates approximately every 2 hours.
API: https://epic.gsfc.nasa.gov/api/natural
"""

import random
import requests
from typing import Optional
from datetime import datetime

from .base import WallpaperSource, ImageResult, ImageCategory


class NasaEpicSource(WallpaperSource):
    """
    NASA EPIC - Real-time full-disc Earth imagery from 1 million miles away.
    
    The DSCOVR satellite captures stunning photos showing the entire
    sunlit face of Earth. No API key needed.
    """

    API_URL = "https://epic.gsfc.nasa.gov/api/natural"
    DATES_URL = "https://epic.gsfc.nasa.gov/api/natural/all"
    ARCHIVE_URL = "https://epic.gsfc.nasa.gov/archive/natural"

    def __init__(self):
        self._dates_cache: Optional[list] = None

    @property
    def name(self) -> str:
        return "NASA EPIC"

    @property
    def source_id(self) -> str:
        return "nasa_epic"

    @property
    def description(self) -> str:
        return "Real-time full-disc Earth photos from 1 million miles away (DSCOVR satellite)"

    @property
    def supports_live(self) -> bool:
        return True

    def _fetch_image_list(self, date: Optional[str] = None) -> list:
        """
        Fetch available images from EPIC API.

        Args:
            date: Optional YYYY-MM-DD date. Omit for the most recent set.
        """
        try:
            url = f"{self.API_URL}/date/{date}" if date else self.API_URL
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"NASA EPIC API error: {e}")
            return []

    def _fetch_available_dates(self) -> list:
        """
        Fetch the list of all dates with available imagery (~3500 days).

        Cached in memory so the archive index is only downloaded once
        per process.
        """
        if self._dates_cache is not None:
            return self._dates_cache
        try:
            response = requests.get(self.DATES_URL, timeout=20)
            response.raise_for_status()
            data = response.json()
            self._dates_cache = [
                entry["date"] for entry in data if entry.get("date")
            ]
        except Exception as e:
            print(f"NASA EPIC dates error: {e}")
            self._dates_cache = []
        return self._dates_cache

    def _build_image_url(self, image_data: dict) -> str:
        """Build the full image URL from API data."""
        date_str = image_data.get("date", "")
        identifier = image_data.get("image", "")
        
        # Parse date to build path: /2024/01/15/png/
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            date_path = dt.strftime("%Y/%m/%d")
        except ValueError:
            # Fallback - try to extract from identifier
            date_path = identifier[:4] + "/" + identifier[4:6] + "/" + identifier[6:8]

        return f"{self.ARCHIVE_URL}/{date_path}/png/{identifier}.png"

    def _parse_entry(self, image_data: dict) -> ImageResult:
        """Convert EPIC API response entry to ImageResult."""
        url = self._build_image_url(image_data)
        date_str = image_data.get("date", "")
        caption = image_data.get("caption", "")
        
        # EPIC provides centroid coordinates
        coords = image_data.get("centroid_coordinates", {})
        lat = coords.get("lat")
        lon = coords.get("lon")

        return ImageResult(
            url=url,
            source_name=self.name,
            title=f"Earth from DSCOVR - {date_str[:10]}",
            description=caption or "Full-disc Earth image from EPIC camera on DSCOVR satellite",
            latitude=lat,
            longitude=lon,
            category=ImageCategory.DAYTIME,  # Always shows sunlit side
            tags=["earth", "satellite", "full-disc", "live", "space"],
            source_id=image_data.get("image", ""),
            attribution="NASA/DSCOVR EPIC - epic.gsfc.nasa.gov",
        )

    def fetch_random(self) -> Optional[ImageResult]:
        """
        Fetch a random EPIC image from anywhere in the archive.

        Draws from ~3500 available dates rather than only the most recent
        set, so this source can supply a fresh image indefinitely.
        """
        dates = self._fetch_available_dates()
        if dates:
            for _ in range(3):
                date = random.choice(dates)
                images = self._fetch_image_list(date)
                if images:
                    return self._parse_entry(random.choice(images))

        # Archive index unavailable - fall back to the latest set
        images = self._fetch_image_list()
        if not images:
            return None
        return self._parse_entry(random.choice(images))

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch the most recent EPIC image."""
        images = self._fetch_image_list()
        if not images:
            return None
        
        # API returns in chronological order, last is most recent
        entry = images[-1]
        return self._parse_entry(entry)
