"""
Time-Aware Wallpaper Mode

Changes wallpaper style based on time of day:
- Sunrise (5-8 AM): warm sunrise shots, golden landscapes
- Daytime (8 AM - 5 PM): vibrant satellite imagery, full-disc Earth
- Sunset (5-8 PM): sunset-facing shots, warm tones
- Night (8 PM - 5 AM): city lights, space imagery, NASA Black Marble

Uses the source registry's category-based fetching to select appropriate images.
"""

from datetime import datetime
from typing import Optional

from sources.base import ImageCategory, ImageResult
from sources.registry import SourceRegistry


class TimeAwareManager:
    """
    Manages time-aware wallpaper selection.
    
    Determines the current time category and requests appropriate
    imagery from the source registry.
    """

    # Time ranges for each category (24-hour format)
    TIME_RANGES = {
        ImageCategory.SUNRISE: (5, 8),    # 5:00 AM - 7:59 AM
        ImageCategory.DAYTIME: (8, 17),   # 8:00 AM - 4:59 PM
        ImageCategory.SUNSET: (17, 20),   # 5:00 PM - 7:59 PM
        ImageCategory.NIGHT: (20, 5),     # 8:00 PM - 4:59 AM (wraps around)
    }

    def __init__(self, registry: SourceRegistry):
        self._registry = registry
        self._enabled = False
        self._custom_ranges = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def get_current_category(self) -> ImageCategory:
        """Determine the current time-of-day category."""
        hour = datetime.now().hour
        
        ranges = self._custom_ranges or self.TIME_RANGES
        
        for category, (start, end) in ranges.items():
            if start < end:
                # Normal range (e.g., 8-17)
                if start <= hour < end:
                    return category
            else:
                # Wrapping range (e.g., 20-5 means 20-24 and 0-5)
                if hour >= start or hour < end:
                    return category

        return ImageCategory.ANY

    def get_category_name(self, category: Optional[ImageCategory] = None) -> str:
        """Get a human-readable name for the current/given category."""
        cat = category or self.get_current_category()
        names = {
            ImageCategory.SUNRISE: "Sunrise",
            ImageCategory.DAYTIME: "Daytime",
            ImageCategory.SUNSET: "Sunset",
            ImageCategory.NIGHT: "Night",
            ImageCategory.ANY: "Any",
        }
        return names.get(cat, "Unknown")

    def fetch_appropriate(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch an image appropriate for the current time of day.
        
        If time-aware mode is disabled, returns a random image.
        """
        if not self._enabled:
            return self._registry.fetch_random(source_id)

        category = self.get_current_category()
        result = self._registry.fetch_by_category(category, source_id)
        
        if result:
            return result

        # Fallback to random if no category match
        return self._registry.fetch_random(source_id)

    def set_custom_ranges(self, ranges: dict) -> None:
        """
        Set custom time ranges.
        
        Args:
            ranges: Dict mapping category names to (start_hour, end_hour) tuples.
                    e.g. {"sunrise": (6, 9), "daytime": (9, 18), ...}
        """
        category_map = {
            "sunrise": ImageCategory.SUNRISE,
            "daytime": ImageCategory.DAYTIME,
            "sunset": ImageCategory.SUNSET,
            "night": ImageCategory.NIGHT,
        }
        
        self._custom_ranges = {}
        for name, (start, end) in ranges.items():
            if name in category_map:
                self._custom_ranges[category_map[name]] = (start, end)

    def get_config(self) -> dict:
        """Get current configuration as a serializable dict."""
        return {
            "enabled": self._enabled,
            "custom_ranges": {
                cat.value: list(hours) 
                for cat, hours in (self._custom_ranges or self.TIME_RANGES).items()
            },
        }

    def load_config(self, config: dict) -> None:
        """Load configuration from dict."""
        self._enabled = config.get("enabled", False)
        if "custom_ranges" in config:
            self.set_custom_ranges(config["custom_ranges"])
