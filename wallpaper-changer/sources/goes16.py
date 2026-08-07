"""
GOES-16/18 satellite source plugin.

NOAA's Geostationary Operational Environmental Satellites provide
stunning full-disk imagery of the Americas. GOES-16 (East) covers
eastern US/Atlantic, GOES-18 (West) covers western US/Pacific.

No API key required. Images updated every 10-15 minutes.
"""

import random
import requests
from typing import Optional
from datetime import datetime, timezone

from .base import WallpaperSource, ImageResult, ImageCategory


class Goes16Source(WallpaperSource):
    """
    GOES-16/18 - NOAA geostationary weather satellites.
    
    Provides beautiful full-disc true-color imagery of the Western Hemisphere.
    Multiple bands available including GeoColor (true color composite).
    """

    # NOAA STAR GOES Image Viewer - direct URLs to latest imagery
    # GeoColor is the true-color composite that looks stunning as wallpaper
    GOES_EAST_URL = "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/FD/GEOCOLOR/latest.jpg"
    GOES_WEST_URL = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/latest.jpg"
    
    # Higher resolution options (5424x5424)
    GOES_EAST_HI = "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/FD/GEOCOLOR/5424x5424.jpg"
    GOES_WEST_HI = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/5424x5424.jpg"
    
    # Medium resolution (1808x1808) - good balance
    GOES_EAST_MED = "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/FD/GEOCOLOR/1808x1808.jpg"
    GOES_WEST_MED = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/1808x1808.jpg"

    # Regional (CONUS) views
    GOES_EAST_CONUS = "https://cdn.star.nesdis.noaa.gov/GOES16/ABI/CONUS/GEOCOLOR/latest.jpg"
    GOES_WEST_CONUS = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/CONUS/GEOCOLOR/latest.jpg"

    SATELLITES = {
        "goes_east": {
            "name": "GOES-16 (East)",
            "full_disc": GOES_EAST_MED,
            "conus": GOES_EAST_CONUS,
            "longitude": -75.2,
            "description": "Eastern Americas, Atlantic Ocean",
        },
        "goes_west": {
            "name": "GOES-18 (West)",
            "full_disc": GOES_WEST_MED,
            "conus": GOES_WEST_CONUS,
            "longitude": -137.2,
            "description": "Western Americas, Pacific Ocean",
        },
    }

    @property
    def name(self) -> str:
        return "GOES Satellites"

    @property
    def source_id(self) -> str:
        return "goes"

    @property
    def description(self) -> str:
        return "NOAA weather satellite full-disc true-color imagery of the Americas (updates every 15 min)"

    @property
    def supports_live(self) -> bool:
        return True

    def _build_result(self, sat_key: str, view: str = "full_disc") -> ImageResult:
        """Build an ImageResult for the given satellite and view."""
        sat = self.SATELLITES[sat_key]
        url = sat[view]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        view_name = "Full Disc" if view == "full_disc" else "Continental US"

        return ImageResult(
            url=url,
            source_name=self.name,
            title=f"{sat['name']} - {view_name} ({now})",
            description=f"GeoColor true-color composite from {sat['name']}. Coverage: {sat['description']}",
            latitude=0.0,
            longitude=sat["longitude"],
            category=ImageCategory.DAYTIME,
            tags=["earth", "satellite", "live", "weather", "americas", "noaa", "goes"],
            source_id=f"{sat_key}_{view}_{now}",
            attribution="NOAA/NESDIS GOES - star.nesdis.noaa.gov",
        )

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random GOES image (random satellite + view)."""
        sat_key = random.choice(list(self.SATELLITES.keys()))
        view = random.choice(["full_disc", "conus"])
        return self._build_result(sat_key, view)

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch the latest GOES full-disc image."""
        # Prefer GOES East full disc (more dramatic views typically)
        sat_key = random.choice(list(self.SATELLITES.keys()))
        return self._build_result(sat_key, "full_disc")
