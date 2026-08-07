"""
Himawari-8 satellite source plugin.

Japanese weather satellite providing full-color true-color Earth imagery.
Updates every 10 minutes. Shows the Asia-Pacific region from geostationary orbit.

No API key required.
"""

import requests
from typing import Optional
from datetime import datetime, timedelta, timezone

from .base import WallpaperSource, ImageResult, ImageCategory


class Himawari8Source(WallpaperSource):
    """
    Himawari-8 - Japanese geostationary weather satellite.
    
    Provides stunning full-disc true-color images of Earth centered on
    the Asia-Pacific region. Updates every 10 minutes.
    """

    # Himawari-8 provides tiled images. For wallpaper use, we use the 
    # single full-disc thumbnail from the NICT viewer.
    BASE_URL = "https://himawari8.nict.go.jp/img/D531106"
    
    # Resolution options: 1d (550px), 2d (1100px), 4d (2200px), 8d (4400px)
    # For wallpaper, 4d gives good quality without massive downloads
    RESOLUTION = "4d"
    THUMBNAIL_RESOLUTION = "1d"

    @property
    def name(self) -> str:
        return "Himawari-8"

    @property
    def source_id(self) -> str:
        return "himawari8"

    @property
    def description(self) -> str:
        return "Near-real-time full-color Earth imagery from Japanese weather satellite (updates every 10 min)"

    @property
    def supports_live(self) -> bool:
        return True

    def _get_latest_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the latest available image."""
        try:
            url = "https://himawari8.nict.go.jp/img/FULL_24h/latest.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            # Returns {"date": "2024-01-15 12:30:00"}
            date_str = data.get("date", "")
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # Fallback: round current UTC time down to nearest 10 minutes, minus 30 min delay
            now = datetime.now(timezone.utc) - timedelta(minutes=30)
            minute = (now.minute // 10) * 10
            return now.replace(minute=minute, second=0, microsecond=0, tzinfo=None)

    def _build_image_url(self, dt: datetime, resolution: str = None) -> str:
        """Build image URL for the given timestamp."""
        res = resolution or self.RESOLUTION
        # Format: /4d/550/2024/01/15/123000_0_0.png (for single tile at 1d)
        # For 1d resolution, it's a single 550x550 image
        date_path = dt.strftime("%Y/%m/%d")
        time_str = dt.strftime("%H%M%S")
        
        if res == "1d":
            return f"{self.BASE_URL}/{res}/550/{date_path}/{time_str}_0_0.png"
        elif res == "2d":
            # 2d is 2x2 tiles, we'll grab the full composite from another endpoint
            return f"{self.BASE_URL}/{res}/550/{date_path}/{time_str}_0_0.png"
        else:
            # For higher resolutions, use the single-tile approach for simplicity
            return f"{self.BASE_URL}/1d/550/{date_path}/{time_str}_0_0.png"

    def _parse_result(self, dt: datetime) -> ImageResult:
        """Create ImageResult for the given timestamp."""
        url = self._build_image_url(dt, "1d")
        
        return ImageResult(
            url=url,
            source_name=self.name,
            title=f"Himawari-8 - {dt.strftime('%Y-%m-%d %H:%M')} UTC",
            description="Full-disc true-color Earth image from Himawari-8 geostationary satellite",
            latitude=0.0,
            longitude=140.7,  # Himawari-8 is positioned at 140.7°E
            category=ImageCategory.DAYTIME,
            tags=["earth", "satellite", "live", "weather", "asia-pacific", "full-disc"],
            source_id=dt.strftime("%Y%m%d_%H%M%S"),
            attribution="Japan Meteorological Agency / NICT - himawari8.nict.go.jp",
        )

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a recent Himawari-8 image (random from last 24 hours)."""
        try:
            latest = self._get_latest_timestamp()
            if not latest:
                return None
            
            # Pick a random image from the last 24 hours (every 10 min = 144 slots)
            import random
            offset_minutes = random.randint(0, 143) * 10
            target = latest - timedelta(minutes=offset_minutes)
            
            return self._parse_result(target)
        except Exception as e:
            print(f"Himawari-8 error: {e}")
            return None

    def fetch_latest(self) -> Optional[ImageResult]:
        """Fetch the most recent Himawari-8 image."""
        try:
            latest = self._get_latest_timestamp()
            if not latest:
                return None
            return self._parse_result(latest)
        except Exception as e:
            print(f"Himawari-8 error: {e}")
            return None
