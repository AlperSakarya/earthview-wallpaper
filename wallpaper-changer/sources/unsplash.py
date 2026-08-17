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
import time
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
    Unsplash - scenery, aerial and space photography.

    Uses GET /photos/random, which returns genuinely random photos rather than
    relevance-ranked search results, and accepts count up to 30. One request
    therefore yields 30 candidates, which are cached and consumed across many
    wallpaper changes. That matters because a demo key allows only 50 requests
    per hour.

    Measured subject accuracy when choosing how to filter:

        query="mountain nature scenery"  30/30 on subject
        query="landscape"                27/30
        topics="wallpapers,nature"       12/30

    The official topics are broad curation buckets, so "wallpapers" also
    contains 3D renders, abstracts and animals. A query is far more precise,
    so queries are used and topics are not.

    Note that /photos/random returns an empty tags list, unlike search, so
    filtering relies on the description and alt description.
    """

    API_URL = "https://api.unsplash.com"

    # Deliberately concrete, since vague terms pull in unrelated subjects.
    SEARCH_TOPICS = [
        "mountain nature scenery", "aerial landscape", "desert dunes landscape",
        "glacier ice landscape", "forest aerial view", "canyon rock landscape",
        "ocean coast aerial", "northern lights aurora", "milky way night sky",
        "nebula galaxy space", "volcano crater landscape", "tropical island aerial",
        "waterfall forest landscape", "fjord mountain coast", "earth from space",
        "storm clouds landscape", "autumn forest landscape", "snow mountain peaks",
    ]

    # A batch is reused until exhausted or stale, to stay well inside the
    # demo key's 50 requests per hour. It is built from several queries and
    # shuffled, because a single query's 30 photos are all on one theme and
    # would otherwise play back as hours of near-identical wallpapers.
    BATCH_SIZE = 30
    BATCH_QUERIES = 3
    BATCH_TTL = 6 * 3600

    def __init__(self):
        self._api_key: Optional[str] = None
        self._batch: List[dict] = []
        self._batch_at: float = 0.0

    @property
    def name(self) -> str:
        return "Unsplash"

    @property
    def source_id(self) -> str:
        return "unsplash"

    @property
    def description(self) -> str:
        return ("Scenery, aerial and space photography "
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
            if key != self._api_key:
                self._batch = []          # a new key invalidates the batch
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
        """Build an ImageResult from an API photo object."""
        url = self._wallpaper_url(photo)
        if not url:
            return None

        description = (photo.get("description")
                       or photo.get("alt_description") or "")
        author = (photo.get("user") or {}).get("name", "Unknown")

        # Many photos carry the place they were taken, which is worth keeping.
        location = photo.get("location") or {}
        position = location.get("position") or {}

        return ImageResult(
            url=url,
            source_name=self.name,
            title=description[:80] if description else "Unsplash photo",
            description=description[:200],
            country=location.get("country") or "",
            region=location.get("city") or "",
            latitude=position.get("latitude"),
            longitude=position.get("longitude"),
            category=self._categorise(self._terms_of(photo)),
            tags=["unsplash"],
            source_id=photo.get("id", ""),
            attribution=f"Photo by {author} on Unsplash",
            download_track_url=(photo.get("links") or {}).get(
                "download_location", ""),
        )

    def _fetch_batch(self, query: str) -> List[dict]:
        """
        Fetch a batch of random photos for a query.

        Uses count, so one request returns up to 30 candidates. The response
        is an array whenever count is supplied, even for a count of one.
        """
        if not self._api_key:
            return []

        try:
            response = requests.get(
                f"{self.API_URL}/photos/random",
                headers={"Authorization": f"Client-ID {self._api_key}"},
                params={
                    "query": query,
                    "count": self.BATCH_SIZE,
                    "orientation": "landscape",
                    "content_filter": "high",
                },
                timeout=25,
            )
            if response.status_code == 401:
                log.warning("Unsplash rejected the API key")
                return []
            if response.status_code == 403:
                log.warning("Unsplash rate limit reached (demo keys allow "
                            "50 requests per hour)")
                return []
            response.raise_for_status()
            photos = response.json()
        except Exception as e:
            log.warning("unsplash request error: %s", e)
            return []

        if isinstance(photos, dict):      # defensive: count omitted
            photos = [photos]

        remaining = response.headers.get("X-Ratelimit-Remaining")
        accepted = [p for p in photos if self._is_acceptable(p)]
        log.debug("unsplash %r: %d of %d on subject, %s requests left",
                  query, len(accepted), len(photos), remaining)
        return accepted

    def _next_photo(self) -> Optional[dict]:
        """Take a photo from the cached batch, refilling it when needed."""
        fresh = (time.time() - self._batch_at) < self.BATCH_TTL
        if not self._batch or not fresh:
            merged: List[dict] = []
            for query in random.sample(self.SEARCH_TOPICS, k=self.BATCH_QUERIES):
                merged.extend(self._fetch_batch(query))
            if not merged:
                return None
            # Shuffle so consecutive wallpapers are not all one theme.
            random.shuffle(merged)
            self._batch = merged
            self._batch_at = time.time()
            log.info("unsplash batch of %d photos from %d queries",
                     len(merged), self.BATCH_QUERIES)

        return self._batch.pop() if self._batch else None

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random scenery, aerial or space photo."""
        if not self._api_key:
            log.debug("no API key configured, skipping")
            return None

        photo = self._next_photo()
        return self._to_result(photo) if photo else None

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """Fetch a photo matching a time-of-day category."""
        if category == ImageCategory.ANY:
            return self.fetch_random()

        queries = {
            ImageCategory.SUNRISE: "sunrise landscape mountains",
            ImageCategory.DAYTIME: "aerial landscape daylight",
            ImageCategory.SUNSET: "sunset landscape golden hour",
            ImageCategory.NIGHT: "milky way night sky landscape",
        }
        query = queries.get(category)
        if not query:
            return self.fetch_random()

        # Category requests bypass the cache, since the cache is per-query.
        batch = self._fetch_batch(query)
        if batch:
            result = self._to_result(random.choice(batch))
            if result:
                result.category = category
                return result

        return self.fetch_random()

    def notify_applied(self, image: ImageResult) -> None:
        """
        Register the download with Unsplash.

        Their API Guidelines require a request to the photo's
        download_location whenever an image is selected for use, naming
        wallpaper selection specifically. This is a tracking callback only;
        the image itself is served from the hotlinked urls.
        """
        track_url = getattr(image, "download_track_url", "")
        if not (track_url and self._api_key):
            return
        try:
            response = requests.get(
                track_url,
                headers={"Authorization": f"Client-ID {self._api_key}"},
                timeout=10,
            )
            log.debug("registered Unsplash download: HTTP %s",
                      response.status_code)
        except Exception as e:
            # Never disrupt the wallpaper change over a tracking call.
            log.debug("could not register Unsplash download: %s", e)
