"""
Unsplash source plugin.

Beautiful photography from Unsplash - aerial, satellite, scenery, nature wallpapers.

Supports two modes:
1. API mode (with free API key from https://unsplash.com/developers) - full access
2. Direct URL mode (no key needed) - uses known Unsplash image URLs with full resolution

The source supports multiple search topics: aerial, satellite, scenery, nature, etc.
Users can configure which topics to pull from.
"""

import random
import re
import requests
from typing import Optional, List
from bs4 import BeautifulSoup

from .base import WallpaperSource, ImageResult, ImageCategory

try:
    from logsetup import get_logger
    log = get_logger("unsplash")
except ImportError:  # standalone use without the app package
    import logging
    log = logging.getLogger("earthview.unsplash")



# Unsplash direct image URL format:
# https://images.unsplash.com/photo-{ID}?w=1920&q=80  (sized)
# https://images.unsplash.com/photo-{ID}  (original full resolution)
#
# To get full resolution for wallpaper, we append ?w=3840&q=90 for 4K quality

# Curated photo IDs covering multiple themes - all verified high-quality wallpapers
CURATED_PHOTOS = {
    "aerial": [
        {"id": "photo-1451187580459-43490279c0fa", "title": "Earth at Night", "category": "night"},
        {"id": "photo-1614730321146-b6fa6a46bcb4", "title": "Earth from Space", "category": "daytime"},
        {"id": "photo-1446776811953-b23d57bd21aa", "title": "Blue Marble", "category": "daytime"},
        {"id": "photo-1517483000871-1dbf64a6e1c6", "title": "Aerial Coastline", "category": "daytime"},
        {"id": "photo-1507400492013-162706c8c05e", "title": "River Delta from Above", "category": "daytime"},
        {"id": "photo-1488866022916-f7f2a4b16a44", "title": "Desert Dunes from Above", "category": "daytime"},
        {"id": "photo-1454789548928-9efd52dc4031", "title": "Earth Horizon from Space", "category": "daytime"},
        {"id": "photo-1504608524841-42fe6f032b4b", "title": "Aerial Turquoise Waters", "category": "daytime"},
    ],
    "scenery": [
        {"id": "photo-1506905925346-21bda4d32df4", "title": "Mountain Peaks", "category": "daytime"},
        {"id": "photo-1470071459604-3b5ec3a7fe05", "title": "Foggy Forest Valley", "category": "sunrise"},
        {"id": "photo-1472214103451-9374bd1c798e", "title": "Green Valley Landscape", "category": "daytime"},
        {"id": "photo-1465056836900-8f1e90f88e42", "title": "Desert Highway", "category": "sunset"},
        {"id": "photo-1433086966358-54859d0ed716", "title": "Waterfall in Forest", "category": "daytime"},
        {"id": "photo-1501785888041-af3ef285b470", "title": "Lake Reflection Mountains", "category": "sunrise"},
        {"id": "photo-1469474968028-56623f02e42e", "title": "Golden Hills Sunset", "category": "sunset"},
        {"id": "photo-1447752875215-b2761acb3c5d", "title": "Autumn Forest Path", "category": "daytime"},
        {"id": "photo-1505765050516-f72dcac9c60e", "title": "Dramatic Cliffs Ocean", "category": "daytime"},
        {"id": "photo-1540206395-68808572332f", "title": "Mountain Lake Sunrise", "category": "sunrise"},
        {"id": "photo-1464822759023-fed622ff2c3b", "title": "Mountain Summit Clouds", "category": "daytime"},
        {"id": "photo-1500534314209-a25ddb2bd429", "title": "Starry Night Mountains", "category": "night"},
        {"id": "photo-1475924156734-496f6cac6ec1", "title": "Northern Lights", "category": "night"},
        {"id": "photo-1509316975850-ff9c5deb0cd9", "title": "Lavender Fields Sunset", "category": "sunset"},
        {"id": "photo-1507003211169-0a1dd7228f2d", "title": "Tropical Beach Paradise", "category": "daytime"},
    ],
    "space": [
        {"id": "photo-1419242902214-272b3f66ee7a", "title": "Milky Way Galaxy", "category": "night"},
        {"id": "photo-1464802686167-b939a6910659", "title": "Nebula", "category": "night"},
        {"id": "photo-1462331940025-496dfbfc7564", "title": "Deep Space Nebula", "category": "night"},
        {"id": "photo-1543722530-d2c3201371e7", "title": "Saturn Rings", "category": "night"},
        {"id": "photo-1516339901601-2e1b62dc0c45", "title": "Galaxy Spiral", "category": "night"},
        {"id": "photo-1502134249126-9f3755a50d78", "title": "Aurora Borealis", "category": "night"},
    ],
    "nature": [
        {"id": "photo-1441974231531-c6227db76b6e", "title": "Sunlit Forest", "category": "daytime"},
        {"id": "photo-1518173946687-a4c8892bbd9f", "title": "Green Mountains", "category": "daytime"},
        {"id": "photo-1431440869543-efaf3388c585", "title": "Ocean Waves", "category": "daytime"},
        {"id": "photo-1470252649378-9c29740c9fa8", "title": "Golden Sunrise Field", "category": "sunrise"},
        {"id": "photo-1500382017468-9049fed747ef", "title": "Golden Fields", "category": "sunset"},
        {"id": "photo-1494500764479-0c8f2919a3d8", "title": "Forest Canopy", "category": "daytime"},
        {"id": "photo-1502239608882-93b729c6af43", "title": "Sunset Above Clouds", "category": "sunset"},
    ],
}


class UnsplashSource(WallpaperSource):
    """
    Unsplash - High-quality photography for wallpapers.
    
    Supports aerial, scenery, nature, and space themes.
    Can work without an API key using curated photo URLs, or with
    an API key for unlimited dynamic searches.
    
    Also supports scraping Unsplash search pages for fresh content.
    """

    API_URL = "https://api.unsplash.com"
    SEARCH_URL = "https://unsplash.com/napi/search/photos"

    # Topics to search when using API/scraping
    SEARCH_TOPICS = [
        "scenery wallpaper",
        "landscape nature",
        "aerial photography",
        "earth from space",
        "mountain landscape",
        "ocean aerial view",
        "northern lights",
        "desert landscape",
        "tropical island aerial",
        "glacier landscape",
        "volcano aerial",
        "canyon landscape",
    ]

    def __init__(self):
        self._api_key: Optional[str] = None
        self._active_topics: List[str] = ["aerial", "scenery", "space", "nature"]
        self._search_enabled = True  # Try to fetch fresh images from Unsplash

    @property
    def name(self) -> str:
        return "Unsplash"

    @property
    def source_id(self) -> str:
        return "unsplash"

    @property
    def description(self) -> str:
        return "High-quality scenery, aerial, nature, and space wallpapers from Unsplash"

    @property
    def requires_api_key(self) -> bool:
        return False  # Works without key using curated + scraping

    @property
    def supports_category(self) -> bool:
        return True

    def configure(self, config: dict) -> None:
        """
        Configure the Unsplash source.
        
        Config options:
            api_key: Unsplash API access key (optional, enables full API access)
            topics: List of active topics ["aerial", "scenery", "space", "nature"]
            search_enabled: Whether to scrape fresh images (default True)
        """
        if "api_key" in config:
            self._api_key = config["api_key"]
        if "topics" in config:
            self._active_topics = config["topics"]
        if "search_enabled" in config:
            self._search_enabled = config["search_enabled"]

    def _get_full_url(self, photo_id: str) -> str:
        """Build a full-resolution wallpaper URL from a photo ID."""
        # Request 4K resolution with high quality
        return f"https://images.unsplash.com/{photo_id}?w=3840&h=2160&fit=crop&q=90"

    def _category_from_string(self, cat_str: str) -> ImageCategory:
        """Convert string category to ImageCategory enum."""
        mapping = {
            "sunrise": ImageCategory.SUNRISE,
            "daytime": ImageCategory.DAYTIME,
            "sunset": ImageCategory.SUNSET,
            "night": ImageCategory.NIGHT,
        }
        return mapping.get(cat_str, ImageCategory.ANY)

    def _parse_curated(self, entry: dict, topic: str) -> ImageResult:
        """Convert curated entry to ImageResult."""
        url = self._get_full_url(entry["id"])
        return ImageResult(
            url=url,
            source_name=self.name,
            title=entry.get("title", "Unsplash Photo"),
            description=f"{topic.capitalize()} photography from Unsplash",
            category=self._category_from_string(entry.get("category", "any")),
            tags=["unsplash", topic],
            source_id=entry["id"],
            attribution="Unsplash - unsplash.com",
        )

    def _fetch_from_api(self, query: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch from Unsplash official API (requires API key)."""
        if not self._api_key:
            return None

        try:
            search_query = query or random.choice(self.SEARCH_TOPICS)
            headers = {"Authorization": f"Client-ID {self._api_key}"}
            params = {
                "query": search_query,
                "orientation": "landscape",
                "per_page": 20,
                "order_by": "relevant",
            }

            response = requests.get(
                f"{self.API_URL}/search/photos",
                headers=headers,
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            photo = random.choice(results)
            # Get the highest quality URL
            urls = photo.get("urls", {})
            url = urls.get("raw", urls.get("full", urls.get("regular", "")))
            
            # Append sizing parameters for wallpaper quality
            if url and "?" not in url:
                url += "?w=3840&h=2160&fit=crop&q=90"
            elif url:
                url += "&w=3840&h=2160&fit=crop&q=90"

            if not url:
                return None

            user_name = photo.get("user", {}).get("name", "Unknown")
            description = photo.get("description") or photo.get("alt_description") or ""

            return ImageResult(
                url=url,
                source_name=self.name,
                title=description[:80] if description else f"Unsplash: {search_query}",
                description=description,
                category=ImageCategory.ANY,
                tags=["unsplash", search_query.split()[0]],
                source_id=photo.get("id", ""),
                attribution=f"Photo by {user_name} on Unsplash",
            )
        except Exception as e:
            log.warning("unsplash api error: %s", e)
            return None

    def _fetch_from_search_page(self, query: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch fresh images by querying Unsplash's internal search API.
        This works without an API key and gives access to the full library.
        Downloads the full-resolution version for wallpaper use.
        """
        try:
            search_query = query or random.choice(self.SEARCH_TOPICS)
            page = random.randint(1, 10)  # Random page for variety
            
            params = {
                "query": search_query,
                "per_page": 20,
                "page": page,
                "orientation": "landscape",
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "application/json",
            }

            response = requests.get(
                self.SEARCH_URL,
                params=params,
                headers=headers,
                timeout=15,
            )
            
            if response.status_code != 200:
                return None

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            # Pick a random photo from results
            photo = random.choice(results)
            urls = photo.get("urls", {})
            
            # Get the raw/full URL for maximum quality wallpaper
            url = urls.get("raw", urls.get("full", urls.get("regular", "")))
            
            if url:
                # Append wallpaper-quality parameters
                separator = "&" if "?" in url else "?"
                url += f"{separator}w=3840&h=2160&fit=crop&q=90"

            if not url:
                return None

            user_name = photo.get("user", {}).get("name", "Unknown")
            description = photo.get("description") or photo.get("alt_description") or ""
            
            # Determine category from color/description hints
            category = ImageCategory.ANY
            desc_lower = (description or "").lower()
            if any(w in desc_lower for w in ["night", "star", "dark", "galaxy", "space"]):
                category = ImageCategory.NIGHT
            elif any(w in desc_lower for w in ["sunrise", "dawn", "morning"]):
                category = ImageCategory.SUNRISE
            elif any(w in desc_lower for w in ["sunset", "dusk", "golden hour"]):
                category = ImageCategory.SUNSET
            elif any(w in desc_lower for w in ["sunny", "bright", "day", "blue sky"]):
                category = ImageCategory.DAYTIME

            return ImageResult(
                url=url,
                source_name=self.name,
                title=description[:80] if description else f"Unsplash: {search_query}",
                description=description[:200] if description else "",
                category=category,
                tags=["unsplash", search_query.replace(" ", "-")],
                source_id=photo.get("id", ""),
                attribution=f"Photo by {user_name} on Unsplash",
            )
        except Exception as e:
            log.warning("unsplash search error: %s", e)
            return None

    def fetch_random(self) -> Optional[ImageResult]:
        """
        Fetch a random high-quality wallpaper from Unsplash.
        
        Priority:
        1. API (if key configured) - best quality + variety
        2. Search page scraping (if enabled) - good variety, full resolution
        3. Curated list - always works, guaranteed quality
        """
        # Try API first
        if self._api_key:
            result = self._fetch_from_api()
            if result:
                return result

        # Try scraping search results for fresh content
        if self._search_enabled:
            result = self._fetch_from_search_page()
            if result:
                return result

        # Fallback to curated photos
        return self._fetch_curated_random()

    def _fetch_curated_random(self) -> Optional[ImageResult]:
        """Get a random image from the curated collection."""
        # Collect all photos from active topics
        all_photos = []
        for topic in self._active_topics:
            if topic in CURATED_PHOTOS:
                for photo in CURATED_PHOTOS[topic]:
                    all_photos.append((photo, topic))

        if not all_photos:
            # Use all topics as fallback
            for topic, photos in CURATED_PHOTOS.items():
                for photo in photos:
                    all_photos.append((photo, topic))

        if all_photos:
            photo, topic = random.choice(all_photos)
            return self._parse_curated(photo, topic)

        return None

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """Fetch an image matching the time-of-day category."""
        if category == ImageCategory.ANY:
            return self.fetch_random()

        # Try search with category-specific query
        if self._search_enabled:
            category_queries = {
                ImageCategory.SUNRISE: "sunrise landscape wallpaper",
                ImageCategory.DAYTIME: "landscape nature bright wallpaper",
                ImageCategory.SUNSET: "sunset landscape golden hour",
                ImageCategory.NIGHT: "night sky stars landscape",
            }
            query = category_queries.get(category)
            if query:
                result = self._fetch_from_search_page(query)
                if result:
                    result.category = category
                    return result

        # Fallback: filter curated by category
        all_photos = []
        for topic in self._active_topics:
            if topic in CURATED_PHOTOS:
                for photo in CURATED_PHOTOS[topic]:
                    if self._category_from_string(photo.get("category", "any")) == category:
                        all_photos.append((photo, topic))

        if all_photos:
            photo, topic = random.choice(all_photos)
            return self._parse_curated(photo, topic)

        return self.fetch_random()
