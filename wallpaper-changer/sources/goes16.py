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

    # NOAA STAR GOES Image Viewer - GeoColor is the true-color composite
    # that looks best as a wallpaper.

    CDN_BASE = "https://cdn.star.nesdis.noaa.gov"

    # NOTE: NOAA replaced GOES-16 with GOES-19 as the GOES-East satellite.
    # Requests to the old GOES16 paths 302-redirect to GOES19, so we target
    # GOES19 directly. Every sector/resolution pair below was verified to
    # return HTTP 200 with image/jpeg content.
    GOES_EAST_MED = f"{CDN_BASE}/GOES19/ABI/FD/GEOCOLOR/1808x1808.jpg"
    GOES_WEST_MED = f"{CDN_BASE}/GOES18/ABI/FD/GEOCOLOR/1808x1808.jpg"
    GOES_EAST_CONUS = f"{CDN_BASE}/GOES19/ABI/CONUS/GEOCOLOR/2500x1500.jpg"
    GOES_WEST_CONUS = f"{CDN_BASE}/GOES18/ABI/CONUS/GEOCOLOR/2500x1500.jpg"

    # Verified sector views: (sector_code, human name, resolution)
    SECTORS = {
        "goes_east": [
            ("FD", "Full Disc", "1808x1808"),
            ("CONUS", "Continental US", "2500x1500"),
            ("ne", "Northeast", "1200x1200"),
            ("se", "Southeast", "1200x1200"),
            ("nr", "Northern Rockies", "1200x1200"),
            ("sr", "Southern Rockies", "1200x1200"),
            ("cgl", "Great Lakes", "1200x1200"),
            ("sp", "Southern Plains", "1200x1200"),
            ("pnw", "Pacific Northwest", "1200x1200"),
            ("psw", "Pacific Southwest", "1200x1200"),
            ("eus", "Eastern US", "1000x1000"),
            ("car", "Caribbean", "1000x1000"),
            ("cam", "Central America", "1000x1000"),
            ("mex", "Mexico", "1000x1000"),
            ("taw", "Tropical Atlantic", "1800x1080"),
        ],
        "goes_west": [
            ("FD", "Full Disc", "1808x1808"),
            ("CONUS", "Continental US", "2500x1500"),
            ("pnw", "Pacific Northwest", "1200x1200"),
            ("psw", "Pacific Southwest", "1200x1200"),
            ("hi", "Hawaii", "1200x1200"),
            ("ak", "Alaska", "1000x1000"),
            ("wus", "Western US", "1000x1000"),
            ("np", "North Pacific", "900x540"),
        ],
    }

    SATELLITES = {
        "goes_east": {
            "name": "GOES-19 (East)",
            "code": "GOES19",
            "full_disc": GOES_EAST_MED,
            "conus": GOES_EAST_CONUS,
            "longitude": -75.2,
            "description": "Eastern Americas, Atlantic Ocean",
        },
        "goes_west": {
            "name": "GOES-18 (West)",
            "code": "GOES18",
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
            url=self._cache_bust(url),
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

    @staticmethod
    def _cache_bust(url: str) -> str:
        """
        Append a time-bucketed cache-busting parameter.

        GOES publishes to fixed 'latest.jpg' style URLs whose *content* changes
        every ~10-15 minutes. Without this, URL-based deduplication would treat
        the feed as a single image and stop using this source after one hit.
        The bucket is aligned to 10 minutes so genuinely new frames yield new
        URLs while rapid repeat calls do not.
        """
        bucket = int(datetime.now(timezone.utc).timestamp() // 600)
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}t={bucket}"

    def _build_sector_result(self, sat_key: str, sector: tuple) -> ImageResult:
        """Build an ImageResult for a regional sector view."""
        sat = self.SATELLITES[sat_key]
        sector_code, sector_name, resolution = sector
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if sector_code in ("FD", "CONUS"):
            path = f"{self.CDN_BASE}/{sat['code']}/ABI/{sector_code}/GEOCOLOR/{resolution}.jpg"
        else:
            path = (f"{self.CDN_BASE}/{sat['code']}/ABI/SECTOR/"
                    f"{sector_code}/GEOCOLOR/{resolution}.jpg")

        return ImageResult(
            url=self._cache_bust(path),
            source_name=self.name,
            title=f"{sat['name']} - {sector_name} ({now})",
            description=(f"GeoColor true-color composite from {sat['name']}, "
                         f"{sector_name} sector."),
            latitude=0.0,
            longitude=sat["longitude"],
            category=ImageCategory.DAYTIME,
            tags=["earth", "satellite", "live", "weather", "americas", "noaa", "goes"],
            source_id=f"{sat_key}_{sector_code}_{now}",
            attribution="NOAA/NESDIS GOES - star.nesdis.noaa.gov",
        )

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random GOES image from any satellite and verified sector."""
        sat_key = random.choice(list(self.SATELLITES.keys()))
        sector = random.choice(self.SECTORS[sat_key])
        return self._build_sector_result(sat_key, sector)

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch the latest GOES full-disc image."""
        sat_key = random.choice(list(self.SATELLITES.keys()))
        return self._build_result(sat_key, "full_disc")
