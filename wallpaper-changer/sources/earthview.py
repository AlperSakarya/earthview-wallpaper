"""
Google Earth View source plugin.

Provides stunning satellite imagery from Google Earth View collection.
Uses the local data.json file with ~1500+ curated satellite photos.
"""

import json
import math
import random
from pathlib import Path
from typing import Optional, List

from .base import WallpaperSource, ImageResult, ImageCategory


class EarthViewSource(WallpaperSource):
    """
    Google Earth View - curated satellite imagery from Google Earth.
    
    This source uses a local JSON database of image metadata from
    earthview.withgoogle.com. No API key required.
    """

    def __init__(self):
        self._data: List[dict] = []
        self._data_path: Optional[Path] = None
        self._load_data()

    def _load_data(self) -> None:
        """Load image data from local JSON file."""
        # Try multiple possible locations
        possible_paths = [
            Path(__file__).parent.parent / "data.json",
            Path(__file__).parent.parent.parent / "earthview.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                self._data_path = path
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        self._data = json.load(f)
                    break
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Failed to load {path}: {e}")
                    continue

    @property
    def name(self) -> str:
        return "Google Earth View"

    @property
    def source_id(self) -> str:
        return "earthview"

    @property
    def description(self) -> str:
        return "Curated satellite imagery from Google Earth - stunning landscapes viewed from space"

    @property
    def supports_location(self) -> bool:
        return True

    @property
    def supports_category(self) -> bool:
        return True

    def is_available(self) -> bool:
        return len(self._data) > 0

    def _parse_entry(self, entry: dict) -> ImageResult:
        """Convert a data.json entry to ImageResult."""
        # Handle both old format (Image URL, Google Maps URL) and new format (image, map)
        if "image" in entry:
            url = entry["image"]
            maps_url = entry.get("map", "")
            country = entry.get("country", "")
            region = entry.get("region", "")
            source_id = str(entry.get("id", ""))
        else:
            raw_url = entry.get("Image URL", "")
            url = f"https://{raw_url}" if not raw_url.startswith("http") else raw_url
            maps_url = entry.get("Google Maps URL", "")
            if maps_url and not maps_url.startswith("http"):
                maps_url = f"https://{maps_url}"
            country = entry.get("Country", "")
            region = entry.get("Region", "")
            source_id = str(entry.get("ID", ""))

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Parse lat/lon from Google Maps URL if available
        lat, lon = self._parse_coordinates(maps_url)

        # Determine category based on location (rough heuristics)
        category = self._guess_category(entry, lat, lon)

        # Build tags from country/region
        tags = []
        if country and country != "-":
            tags.append(country.lower())
        if region and region != "-":
            tags.append(region.lower())

        return ImageResult(
            url=url,
            source_name=self.name,
            title=f"Earth View - {region if region and region != '-' else country}",
            description=f"Satellite view of {region}, {country}" if region and region != "-" else f"Satellite view of {country}",
            country=country,
            region=region,
            latitude=lat,
            longitude=lon,
            maps_url=maps_url,
            category=category,
            tags=tags,
            source_id=source_id,
            attribution="Google Earth View - earthview.withgoogle.com",
        )

    def _parse_coordinates(self, maps_url: str) -> tuple:
        """Extract lat/lon from Google Maps URL."""
        try:
            if "@" in maps_url:
                coords_part = maps_url.split("@")[1].split("/")[0]
                parts = coords_part.split(",")
                if len(parts) >= 2:
                    return float(parts[0]), float(parts[1])
        except (IndexError, ValueError):
            pass
        return None, None

    def _guess_category(self, entry: dict, lat: Optional[float], 
                        lon: Optional[float]) -> ImageCategory:
        """
        Guess image category based on content/location.
        Night images tend to be city shots, polar regions are icy/daytime, etc.
        """
        region = entry.get("region", entry.get("Region", "")).lower()
        country = entry.get("country", entry.get("Country", "")).lower()

        # Cities tend to look best at night
        city_keywords = ["chicago", "tokyo", "new york", "london", "paris", 
                         "shanghai", "dubai", "los angeles"]
        if any(kw in region.lower() or kw in country.lower() for kw in city_keywords):
            return ImageCategory.NIGHT

        # Polar regions are bright daytime
        if lat is not None and abs(lat) > 60:
            return ImageCategory.DAYTIME

        # Desert/arid regions are vivid in daytime
        desert_countries = ["libya", "egypt", "chad", "saudi arabia", "namibia"]
        if country in desert_countries:
            return ImageCategory.DAYTIME

        return ImageCategory.ANY

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random Earth View image."""
        if not self._data:
            return None

        entry = random.choice(self._data)
        return self._parse_entry(entry)

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """Fetch an image matching the given category."""
        if not self._data:
            return None

        if category == ImageCategory.ANY:
            return self.fetch_random()

        # Filter entries that match the category
        matching = []
        for entry in self._data:
            lat, lon = self._parse_coordinates(
                entry.get("map", entry.get("Google Maps URL", ""))
            )
            guessed = self._guess_category(entry, lat, lon)
            if guessed == category or guessed == ImageCategory.ANY:
                matching.append(entry)

        if matching:
            entry = random.choice(matching)
            return self._parse_entry(entry)

        # Fallback to random
        return self.fetch_random()

    def fetch_near_location(self, latitude: float, longitude: float,
                            radius_km: float = 500) -> Optional[ImageResult]:
        """Fetch an image near the given coordinates."""
        if not self._data:
            return None

        candidates = []
        for entry in self._data:
            maps_url = entry.get("map", entry.get("Google Maps URL", ""))
            lat, lon = self._parse_coordinates(maps_url)
            if lat is not None and lon is not None:
                dist = self._haversine(latitude, longitude, lat, lon)
                if dist <= radius_km:
                    candidates.append((dist, entry))

        if candidates:
            # Sort by distance and sample from a wide pool of nearby images.
            # A narrow pool (e.g. closest 5) causes the same handful of
            # locations to repeat endlessly in location mode.
            candidates.sort(key=lambda x: x[0])
            pool_size = max(40, len(candidates) // 2)
            top = candidates[:min(pool_size, len(candidates))]
            _, entry = random.choice(top)
            return self._parse_entry(entry)

        # No nearby images - expand search or return random
        return self.fetch_random()

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in km using Haversine formula."""
        R = 6371  # Earth's radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
