"""
Unsplash source plugin.

Scenery, aerial and space photography, discovered dynamically through the
Unsplash search API. No image identifiers are stored in this file: every
wallpaper comes from a live search.

A free API key is required, from https://unsplash.com/developers, entered
under Preferences > Sources. Without one this source reports itself
unavailable and is skipped.

There is deliberately no keyless fallback. Unsplash closed every keyless
route: unsplash.com/napi/search answers 307 to non-browser clients,
source.unsplash.com is retired and answers 503, and api.unsplash.com answers
401 without a Client-ID. Photo identifiers cannot be guessed either, as they
are opaque rather than sequential. For a large keyless pool use the Wikimedia
Commons source, which needs no key.

Results are screened to reject people-centric photographs, which Unsplash
returns freely for queries about landscapes.
"""

import random
import requests
from typing import Optional, List

from .base import WallpaperSource, ImageResult, ImageCategory

try:
    from logsetup import get_logger
    log = get_logger("unsplash")
except ImportError:  # standalone use without the app package
    import logging
    log = logging.getLogger("earthview.unsplash")


# Words indicating a photo is centred on people rather than scenery. Checked
# against the description and tags the API returns.
PEOPLE_TERMS = {
    "man", "woman", "men", "women", "person", "people", "boy", "girl",
    "portrait", "face", "smile", "smiling", "selfie", "model", "headshot",
    "beard", "hair", "haircut", "makeup", "skin", "lips", "eyes",
    "child", "children", "baby", "kid", "family", "couple", "wedding",
    "human", "female", "male", "guy", "lady", "hands", "feet",
    "fashion", "clothing", "shirt", "dress", "suit",
}

# Words confirming a photo is the kind of scenery this application is for.
SUBJECT_TERMS = {
    "landscape", "mountain", "mountains", "ocean", "sea", "coast", "beach",
    "forest", "tree", "trees", "desert", "dune", "canyon", "valley",
    "glacier", "ice", "snow", "lake", "river", "waterfall", "island",
    "aerial", "drone", "satellite", "earth", "space", "galaxy", "nebula",
    "stars", "sky", "clouds", "sunset", "sunrise", "aurora", "volcano",
    "field", "meadow", "hill", "cliff", "reef", "lagoon", "fjord",
    "nature", "scenery", "horizon", "terrain", "geology", "planet",
}


class UnsplashSource(WallpaperSource):
    """
    Unsplash - scenery, aerial and space photography via live search.

    Requires a free API key. Filters out people-centric results.
    """

    API_URL = "https://api.unsplash.com"

    SEARCH_TOPICS = [
        "aerial landscape", "mountain landscape", "earth from space",
        "ocean aerial view", "desert landscape", "glacier landscape",
        "forest aerial", "canyon landscape", "northern lights",
        "nebula galaxy", "volcano aerial", "tropical island aerial",
        "coastline aerial", "sand dunes aerial", "fjord landscape",
        "waterfall landscape", "starry night landscape", "storm clouds",
    ]

    def __init__(self):
        self._api_key: Optional[str] = None

    @property
    def name(self) -> str:
        return "Unsplash"

    @property
    def source_id(self) -> str:
        return "unsplash"

    @property
    def description(self) -> str:
        return ("Scenery, aerial and space photography via live search "
                "(needs a free key from unsplash.com/developers)")

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def supports_category(self) -> bool:
        return True

    def is_available(self) -> bool:
        """Unusable without a key, so the rotation skips it entirely."""
        return bool(self._api_key)

    def configure(self, config: dict) -> None:
        """Accept the Unsplash API access key."""
        if "api_key" in config:
            key = (config["api_key"] or "").strip()
            self._api_key = key or None

    @staticmethod
    def _terms_of(photo: dict) -> set:
        """Lowercase words describing a photo, from its text and tags."""
        words = set()
        for field in ("description", "alt_description"):
            text = photo.get(field) or ""
            words.update(w.strip(".,!?()[]'\"").lower() for w in text.split())
        for tag in photo.get("tags") or []:
            words.update((tag.get("title") or "").lower().split())
        return words

    def _is_acceptable(self, photo: dict) -> bool:
        """
        Reject people-centric photos.

        A photo is rejected when it mentions people without also mentioning
        scenery, and when it carries no usable description at all, since then
        its subject cannot be established.
        """
        words = self._terms_of(photo)
        if not words:
            return False
        if (words & PEOPLE_TERMS) and not (words & SUBJECT_TERMS):
            return False
        return bool(words & SUBJECT_TERMS)

    def _wallpaper_url(self, photo: dict) -> Optional[str]:
        """Highest quality URL, sized for a wallpaper."""
        urls = photo.get("urls", {})
        url = urls.get("raw") or urls.get("full") or urls.get("regular")
        if not url:
            return None
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}w=3840&h=2160&fit=crop&q=90"

    @staticmethod
    def _categorise(words: set) -> ImageCategory:
        """Infer a time-of-day category from descriptive words."""
        if words & {"night", "stars", "galaxy", "nebula", "aurora", "milky"}:
            return ImageCategory.NIGHT
        if words & {"sunrise", "dawn", "morning"}:
            return ImageCategory.SUNRISE
        if words & {"sunset", "dusk", "evening", "golden"}:
            return ImageCategory.SUNSET
        if words & {"day", "daylight", "sunny", "bright"}:
            return ImageCategory.DAYTIME
        return ImageCategory.ANY

    def _to_result(self, photo: dict) -> Optional[ImageResult]:
        """Build an ImageResult from a live API photo object."""
        url = self._wallpaper_url(photo)
        if not url:
            return None

        description = (photo.get("description")
                       or photo.get("alt_description") or "")
        author = (photo.get("user") or {}).get("name", "Unknown")

        return ImageResult(
            url=url,
            source_name=self.name,
            title=description[:80] if description else "Unsplash photo",
            description=description[:200],
            category=self._categorise(self._terms_of(photo)),
            tags=["unsplash"],
            source_id=photo.get("id", ""),
            attribution=f"Photo by {author} on Unsplash",
        )

    def _search(self, query: str) -> List[dict]:
        """Run a live search, returning only acceptable photos."""
        if not self._api_key:
            return []

        try:
            response = requests.get(
                f"{self.API_URL}/search/photos",
                headers={"Authorization": f"Client-ID {self._api_key}"},
                params={
                    "query": query,
                    "orientation": "landscape",
                    "per_page": 30,
                    # Deep pages drift off topic, so stay near the top.
                    "page": random.randint(1, 5),
                    "content_filter": "high",
                },
                timeout=20,
            )
            if response.status_code == 401:
                log.warning("Unsplash rejected the API key")
                return []
            response.raise_for_status()
            results = response.json().get("results", [])
        except Exception as e:
            log.warning("unsplash search error: %s", e)
            return []

        accepted = [p for p in results if self._is_acceptable(p)]
        if len(results) != len(accepted):
            log.debug("rejected %d of %d off-subject results for %r",
                      len(results) - len(accepted), len(results), query)
        return accepted

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random scenery, aerial or space photo from live search."""
        if not self._api_key:
            log.debug("no API key configured, skipping")
            return None

        topics = random.sample(self.SEARCH_TOPICS,
                               k=min(3, len(self.SEARCH_TOPICS)))
        for query in topics:
            photos = self._search(query)
            if photos:
                return self._to_result(random.choice(photos))

        log.info("no acceptable results for %s", ", ".join(topics))
        return None

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """Fetch a photo matching a time-of-day category."""
        if category == ImageCategory.ANY:
            return self.fetch_random()

        queries = {
            ImageCategory.SUNRISE: "sunrise landscape",
            ImageCategory.DAYTIME: "aerial landscape daylight",
            ImageCategory.SUNSET: "sunset landscape golden hour",
            ImageCategory.NIGHT: "night sky stars landscape",
        }
        query = queries.get(category)
        if not query:
            return self.fetch_random()

        photos = self._search(query)
        if photos:
            result = self._to_result(random.choice(photos))
            if result:
                result.category = category
                return result

        return self.fetch_random()
