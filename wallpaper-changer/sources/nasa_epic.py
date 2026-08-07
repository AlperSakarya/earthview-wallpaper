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
    ARCHIVE_URL = "https://epic.gsfc.nasa.gov/archive/natural"

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

    def _fetch_image_list(self) -> list:
        """Fetch available images from EPIC API."""
        try:
            response = requests.get(self.API_URL, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"NASA EPIC API error: {e}")
            return []

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
        """Fetch a random recent EPIC image."""
        images = self._fetch_image_list()
        if not images:
            return None
        
        entry = random.choice(images)
        return self._parse_entry(entry)

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch the most recent EPIC image."""
        images = self._fetch_image_list()
        if not images:
            return None
        
        # API returns in chronological order, last is most recent
        entry = images[-1]
        return self._parse_entry(entry)
