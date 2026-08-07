"""
Base class for all wallpaper sources.

Each source must subclass WallpaperSource and implement the required methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import time


class ImageCategory(Enum):
    """Categories for time-aware wallpaper selection."""
    SUNRISE = "sunrise"
    DAYTIME = "daytime"
    SUNSET = "sunset"
    NIGHT = "night"
    ANY = "any"


@dataclass
class ImageResult:
    """Standardized result from any wallpaper source."""
    url: str
    source_name: str
    title: str = ""
    description: str = ""
    country: str = ""
    region: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    maps_url: str = ""
    category: ImageCategory = ImageCategory.ANY
    tags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    source_id: str = ""  # unique ID within the source
    attribution: str = ""

    @property
    def location_str(self) -> str:
        """Human-readable location string."""
        parts = [p for p in [self.region, self.country] if p and p != "-"]
        return ", ".join(parts) if parts else "Unknown location"

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            'url': self.url,
            'source_name': self.source_name,
            'title': self.title,
            'description': self.description,
            'country': self.country,
            'region': self.region,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'maps_url': self.maps_url,
            'category': self.category.value,
            'tags': self.tags,
            'timestamp': self.timestamp,
            'source_id': self.source_id,
            'attribution': self.attribution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ImageResult':
        """Deserialize from dictionary."""
        data = data.copy()
        data['category'] = ImageCategory(data.get('category', 'any'))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class WallpaperSource(ABC):
    """
    Abstract base class for wallpaper image sources.
    
    Each source must implement:
        - name: Human-readable name
        - source_id: Unique identifier string
        - fetch_random(): Get a random image
        
    Optionally implement:
        - fetch_latest(): Get the most recent image (for live sources)
        - fetch_by_category(): Get image matching a time category
        - fetch_near_location(): Get image near coordinates
        - requires_api_key: Whether this source needs configuration
        - is_available(): Check if source is currently usable
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name."""
        pass

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique source identifier (lowercase, no spaces)."""
        pass

    @property
    def description(self) -> str:
        """Short description of this source."""
        return ""

    @property
    def requires_api_key(self) -> bool:
        """Whether this source requires an API key to function."""
        return False

    @property
    def supports_live(self) -> bool:
        """Whether this source provides real-time/recent imagery."""
        return False

    @property
    def supports_location(self) -> bool:
        """Whether this source can fetch by geographic coordinates."""
        return False

    @property
    def supports_category(self) -> bool:
        """Whether this source can filter by time-of-day category."""
        return False

    def is_available(self) -> bool:
        """Check if this source is currently usable (has data, keys, network, etc.)."""
        return True

    @abstractmethod
    def fetch_random(self) -> Optional[ImageResult]:
        """
        Fetch a random image from this source.
        
        Returns:
            ImageResult on success, None on failure.
        """
        pass

    def fetch_latest(self) -> Optional[ImageResult]:
        """
        Fetch the most recent/current image (for live satellite feeds).
        
        Returns:
            ImageResult on success, None if not supported or failed.
        """
        return None

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """
        Fetch an image matching a time-of-day category.
        
        Args:
            category: The desired image category (sunrise, daytime, night, etc.)
            
        Returns:
            ImageResult on success, None if not supported or no match.
        """
        return self.fetch_random()

    def fetch_near_location(self, latitude: float, longitude: float,
                            radius_km: float = 500) -> Optional[ImageResult]:
        """
        Fetch an image near the given coordinates.
        
        Args:
            latitude: Target latitude
            longitude: Target longitude
            radius_km: Search radius in kilometers
            
        Returns:
            ImageResult on success, None if not supported or no match.
        """
        return None

    def configure(self, config: dict) -> None:
        """
        Apply configuration to this source (API keys, preferences, etc.)
        
        Args:
            config: Dictionary of configuration values.
        """
        pass
