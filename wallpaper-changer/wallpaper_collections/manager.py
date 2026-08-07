"""
Collection Manager - loads, manages, and provides access to themed image collections.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sources.base import ImageResult, ImageCategory


@dataclass
class Collection:
    """A themed collection of curated images."""
    id: str
    name: str
    description: str
    icon: str  # optional icon identifier for menu display
    images: List[dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.images)

    def get_random(self) -> Optional[ImageResult]:
        """Get a random image from this collection."""
        if not self.images:
            return None
        entry = random.choice(self.images)
        return self._to_image_result(entry)

    def get_all(self) -> List[ImageResult]:
        """Get all images in this collection."""
        return [self._to_image_result(e) for e in self.images]

    def _to_image_result(self, entry: dict) -> ImageResult:
        """Convert collection entry to ImageResult."""
        category_str = entry.get("category", "any")
        category_map = {
            "sunrise": ImageCategory.SUNRISE,
            "daytime": ImageCategory.DAYTIME,
            "sunset": ImageCategory.SUNSET,
            "night": ImageCategory.NIGHT,
            "any": ImageCategory.ANY,
        }
        
        return ImageResult(
            url=entry["url"],
            source_name=f"Collection: {self.name}",
            title=entry.get("title", ""),
            description=entry.get("description", ""),
            country=entry.get("country", ""),
            region=entry.get("region", ""),
            latitude=entry.get("latitude"),
            longitude=entry.get("longitude"),
            maps_url=entry.get("maps_url", ""),
            category=category_map.get(category_str, ImageCategory.ANY),
            tags=entry.get("tags", []) + self.tags,
            source_id=entry.get("id", ""),
            attribution=entry.get("attribution", ""),
        )

    def to_dict(self) -> dict:
        """Serialize collection to dict for JSON storage."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "tags": self.tags,
            "images": self.images,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Collection':
        """Deserialize collection from dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            icon=data.get("icon", ""),
            images=data.get("images", []),
            tags=data.get("tags", []),
        )


class CollectionManager:
    """
    Manages themed image collections.
    
    Collections are stored as JSON files in the collections/ directory.
    Users can also create custom collections via the preferences UI.
    """

    def __init__(self, collections_dir: Optional[Path] = None):
        self._collections_dir = collections_dir or Path(__file__).parent
        self._collections: Dict[str, Collection] = {}
        self._user_collections_dir = Path.home() / ".config" / "earthview" / "collections"
        self.load_collections()

    def load_collections(self) -> None:
        """Load all collection JSON files."""
        self._collections.clear()

        # Load built-in collections
        self._load_from_dir(self._collections_dir)

        # Load user collections
        if self._user_collections_dir.exists():
            self._load_from_dir(self._user_collections_dir)

    def _load_from_dir(self, directory: Path) -> None:
        """Load collections from a directory."""
        for json_file in directory.glob("*.json"):
            if json_file.name.startswith("_"):
                continue
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                collection = Collection.from_dict(data)
                self._collections[collection.id] = collection
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f"Warning: Failed to load collection {json_file}: {e}")

    @property
    def all_collections(self) -> Dict[str, Collection]:
        """All loaded collections."""
        return self._collections.copy()

    @property
    def collection_names(self) -> List[str]:
        """List of all collection IDs."""
        return list(self._collections.keys())

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a specific collection by ID."""
        return self._collections.get(collection_id)

    def fetch_random(self, collection_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch a random image from collections.
        
        Args:
            collection_id: If specified, fetch only from this collection.
                          Otherwise, pick from all collections.
        """
        if collection_id:
            collection = self._collections.get(collection_id)
            if collection:
                return collection.get_random()
            return None

        all_collections = list(self._collections.values())
        if not all_collections:
            return None

        # Pick a random collection, then a random image from it
        collection = random.choice(all_collections)
        return collection.get_random()

    def create_collection(self, collection_id: str, name: str,
                          description: str, icon: str = "",
                          tags: Optional[List[str]] = None) -> Collection:
        """Create a new user collection."""
        collection = Collection(
            id=collection_id,
            name=name,
            description=description,
            icon=icon,
            tags=tags or [],
        )
        self._collections[collection_id] = collection
        return collection

    def add_to_collection(self, collection_id: str, image: ImageResult) -> bool:
        """Add an image to a collection."""
        collection = self._collections.get(collection_id)
        if not collection:
            return False

        entry = {
            "url": image.url,
            "title": image.title,
            "description": image.description,
            "country": image.country,
            "region": image.region,
            "latitude": image.latitude,
            "longitude": image.longitude,
            "maps_url": image.maps_url,
            "category": image.category.value,
            "tags": image.tags,
            "id": image.source_id,
            "attribution": image.attribution,
        }
        collection.images.append(entry)
        return True

    def save_collection(self, collection_id: str) -> bool:
        """Save a collection to disk (user collections directory)."""
        collection = self._collections.get(collection_id)
        if not collection:
            return False

        self._user_collections_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._user_collections_dir / f"{collection_id}.json"

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(collection.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Error saving collection: {e}")
            return False

    def remove_collection(self, collection_id: str) -> bool:
        """Remove a user collection."""
        if collection_id not in self._collections:
            return False

        # Remove from memory
        del self._collections[collection_id]

        # Remove file if it exists in user dir
        user_file = self._user_collections_dir / f"{collection_id}.json"
        if user_file.exists():
            user_file.unlink()
            return True

        return True
