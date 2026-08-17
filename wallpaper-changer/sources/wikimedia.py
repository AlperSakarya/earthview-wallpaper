"""
Wikimedia Commons source plugin.

A large keyless pool of landscape and astronomy photography drawn from
Commons' peer-reviewed "Featured pictures" and "Quality images" categories.
Typically 1,500 to 3,000 images, at native resolutions of 4-6K.

No API key is required. Commons rate limits aggressive clients with HTTP 429,
so the category listing is cached on disk and refreshed weekly rather than
being fetched for every wallpaper change.

Only landscape, nature and astronomy categories are used, so people-centric
photographs do not enter the pool.
"""

import json
import random
import time
import urllib.parse
from pathlib import Path
from typing import Optional, List

import requests

from .base import WallpaperSource, ImageResult, ImageCategory

try:
    from logsetup import get_logger
    log = get_logger("wikimedia")
except ImportError:  # standalone use without the app package
    import logging
    log = logging.getLogger("earthview.wikimedia")


# Categories verified to exist and return files. Commons category names are
# exact, and a wrong name silently yields nothing, so these are checked rather
# than guessed.
CATEGORIES = [
    "Featured pictures of landscapes",
    "Quality images of landscapes",
    "Featured pictures of mountains",
    "Featured pictures of clouds",
    "Featured pictures of waterfalls",
    "Featured pictures of lakes",
    "Featured pictures of coasts",
    "Featured pictures of forests",
    "Featured pictures of rivers",
    "Featured pictures of islands",
    "Featured pictures of deserts of the world",
    "Featured pictures of astronomy",
    "Featured pictures supported by Wikipedia Aerial photographs",
]

CACHE_TTL = 7 * 24 * 3600     # refresh the listing weekly
PAGE_LIMIT = 500              # Commons caps a single listing request here


class WikimediaSource(WallpaperSource):
    """
    Wikimedia Commons - curated landscape and astronomy photography.

    Draws from Featured pictures and Quality images categories, which are
    peer-reviewed, so the pool is large without being low quality.
    """

    API_URL = "https://commons.wikimedia.org/w/api.php"
    # Wikimedia's user agent policy requires identification and a contact
    # point. A short or absent value is answered with 429 or 403.
    USER_AGENT = ("earthview-wallpaper/2.x "
                  "(https://github.com/AlperSakarya/earthview)")

    def __init__(self):
        self._cache_file = (
            Path.home() / ".cache" / "earthview" / "wikimedia_files.json"
        )
        self._titles: List[str] = []
        self._loaded = False

    @property
    def name(self) -> str:
        return "Wikimedia Commons"

    @property
    def source_id(self) -> str:
        return "wikimedia"

    @property
    def description(self) -> str:
        return ("Peer-reviewed landscape and astronomy photography from "
                "Wikimedia Commons, no API key needed")

    @property
    def supports_category(self) -> bool:
        return True

    def is_available(self) -> bool:
        """Available once a pool has been built, or can still be built."""
        self._ensure_titles()
        return bool(self._titles)

    # -- listing ----------------------------------------------------------

    def _request(self, params: dict) -> Optional[dict]:
        """One API call, tolerating rate limits."""
        params.setdefault("format", "json")
        try:
            response = requests.get(
                self.API_URL, params=params,
                headers={"User-Agent": self.USER_AGENT}, timeout=30)
            if response.status_code == 429:
                log.warning("Commons rate limited this request")
                return None
            response.raise_for_status()
            return response.json()
        except Exception as e:
            log.warning("commons request failed: %s", e)
            return None

    def _fetch_category(self, category: str) -> List[str]:
        """File titles in one category, following pagination."""
        titles: List[str] = []
        cont = None

        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmlimit": PAGE_LIMIT,
                "cmtype": "file",
            }
            if cont:
                params["cmcontinue"] = cont

            data = self._request(params)
            if not data:
                break

            members = data.get("query", {}).get("categorymembers", [])
            titles.extend(m["title"] for m in members)

            cont = data.get("continue", {}).get("cmcontinue")
            if not cont:
                break
            # Be a considerate client; Commons returns 429 when hammered.
            time.sleep(0.5)

        return titles

    def _build_pool(self) -> List[str]:
        """Assemble the file pool across all categories."""
        titles: List[str] = []
        for category in CATEGORIES:
            found = self._fetch_category(category)
            if found:
                log.debug("commons category %r: %d files", category, len(found))
                titles.extend(found)
            else:
                log.debug("commons category %r returned nothing", category)
            time.sleep(0.4)

        unique = sorted(set(titles))
        log.info("commons pool built: %d unique images from %d categories",
                 len(unique), len(CATEGORIES))
        return unique

    def _ensure_titles(self) -> None:
        """Load the pool from cache, rebuilding when stale or absent."""
        if self._loaded and self._titles:
            return

        # Cached and fresh?
        try:
            if self._cache_file.exists():
                payload = json.loads(self._cache_file.read_text())
                age = time.time() - payload.get("built", 0)
                cached = payload.get("titles", [])
                if cached and age < CACHE_TTL:
                    self._titles = cached
                    self._loaded = True
                    log.debug("commons pool from cache: %d images", len(cached))
                    return
        except (json.JSONDecodeError, OSError) as e:
            log.debug("commons cache unreadable: %s", e)

        titles = self._build_pool()

        if titles:
            self._titles = titles
            try:
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._cache_file.write_text(
                    json.dumps({"built": time.time(), "titles": titles}))
            except OSError as e:
                log.debug("could not write commons cache: %s", e)
        elif self._cache_file.exists():
            # Rebuild failed, for example rate limited. Reuse the stale cache
            # rather than dropping the source out of rotation.
            try:
                payload = json.loads(self._cache_file.read_text())
                self._titles = payload.get("titles", [])
                log.info("commons rebuild failed, reusing %d cached images",
                         len(self._titles))
            except (json.JSONDecodeError, OSError):
                pass

        self._loaded = True

    # -- fetching ---------------------------------------------------------

    def _resolve(self, title: str) -> Optional[ImageResult]:
        """Turn a file title into a usable image URL and metadata."""
        data = self._request({
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 3840,
        })
        if not data:
            return None

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [None])[0]
            if not info:
                continue

            # Prefer the scaled 3840px render over a possibly enormous original.
            url = info.get("thumburl") or info.get("url")
            if not url:
                continue

            meta = info.get("extmetadata") or {}
            def field(key):
                return (meta.get(key) or {}).get("value", "")

            # Strip the "File:" prefix and extension for a readable title.
            label = title.split(":", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
            artist = field("Artist")
            # Artist arrives as HTML; keep it short and plain.
            if artist:
                import re
                artist = re.sub(r"<[^>]+>", "", artist).strip()[:60]

            words = set(label.lower().split())
            return ImageResult(
                url=url,
                source_name=self.name,
                title=label[:80],
                description=field("ImageDescription")[:200] or label[:200],
                category=self._categorise(words),
                tags=["wikimedia", "commons"],
                source_id=title,
                attribution=(f"{artist} via Wikimedia Commons"
                             if artist else "Wikimedia Commons"),
            )
        return None

    @staticmethod
    def _categorise(words: set) -> ImageCategory:
        """Infer a time-of-day category from the file name."""
        if words & {"night", "stars", "starry", "milky", "aurora", "nebula",
                    "galaxy", "moon", "moonlight"}:
            return ImageCategory.NIGHT
        if words & {"sunrise", "dawn", "morning"}:
            return ImageCategory.SUNRISE
        if words & {"sunset", "dusk", "evening", "twilight"}:
            return ImageCategory.SUNSET
        return ImageCategory.ANY

    def fetch_random(self) -> Optional[ImageResult]:
        """Fetch a random image from the pool."""
        self._ensure_titles()
        if not self._titles:
            return None

        # A title can occasionally fail to resolve, so try a few.
        for _ in range(4):
            result = self._resolve(random.choice(self._titles))
            if result:
                return result
        return None

    def fetch_by_category(self, category: ImageCategory) -> Optional[ImageResult]:
        """Fetch an image whose name suggests the requested time of day."""
        self._ensure_titles()
        if not self._titles:
            return None
        if category == ImageCategory.ANY:
            return self.fetch_random()

        matching = [t for t in self._titles
                    if self._categorise(set(t.lower().split())) == category]
        if matching:
            for _ in range(4):
                result = self._resolve(random.choice(matching))
                if result:
                    return result

        return self.fetch_random()

    @property
    def pool_size(self) -> int:
        """Number of images currently in the pool."""
        self._ensure_titles()
        return len(self._titles)
