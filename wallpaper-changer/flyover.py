"""
Location-Aware / Fly-Over Mode

Two modes of operation:
1. Location-Aware: Uses IP geolocation to show satellite imagery near the user
2. Fly-Over: Simulates a flight path along predefined routes, advancing
   with each wallpaper change

Predefined routes include:
- Nile River (source to delta)
- Coastline tours (Mediterranean, Pacific Rim)
- Trans-Siberian Railway
- Silk Road
- Great Wall of China
- Andes Mountains
"""

import json
import math
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

from sources.base import ImageResult
from sources.registry import SourceRegistry


@dataclass
class RoutePoint:
    """A point along a fly-over route."""
    latitude: float
    longitude: float
    name: str = ""
    description: str = ""


@dataclass
class FlyOverRoute:
    """A predefined fly-over route."""
    id: str
    name: str
    description: str
    points: List[RoutePoint]

    @property
    def total_points(self) -> int:
        return len(self.points)


# Predefined fly-over routes
ROUTES = {
    "nile_river": FlyOverRoute(
        id="nile_river",
        name="Nile River",
        description="Follow the Nile from Lake Victoria to the Mediterranean Delta",
        points=[
            RoutePoint(-2.0, 33.0, "Lake Victoria", "Source of the White Nile"),
            RoutePoint(2.0, 32.5, "South Sudan", "Sudd wetlands"),
            RoutePoint(9.0, 32.5, "Blue Nile confluence", "Khartoum"),
            RoutePoint(15.6, 32.5, "Nubian Desert", "Ancient kingdoms"),
            RoutePoint(19.5, 30.4, "Nile Valley", "Temple region"),
            RoutePoint(24.0, 32.9, "Luxor region", "Valley of the Kings"),
            RoutePoint(27.2, 31.2, "Cairo approach", "Pyramids of Giza"),
            RoutePoint(30.0, 31.0, "Nile Delta", "Mediterranean coast"),
            RoutePoint(31.4, 30.5, "Alexandria", "Mediterranean Sea"),
        ],
    ),
    "mediterranean_coast": FlyOverRoute(
        id="mediterranean_coast",
        name="Mediterranean Coastline",
        description="Tour the Mediterranean coast from Gibraltar to Istanbul",
        points=[
            RoutePoint(36.0, -5.5, "Gibraltar", "Strait of Gibraltar"),
            RoutePoint(36.7, -4.4, "Malaga", "Costa del Sol"),
            RoutePoint(38.3, -0.5, "Valencia", "Spanish coast"),
            RoutePoint(41.4, 2.2, "Barcelona", "Catalonia"),
            RoutePoint(43.3, 5.4, "Marseille", "French Riviera"),
            RoutePoint(43.7, 7.3, "Nice", "Cote d'Azur"),
            RoutePoint(41.9, 12.5, "Rome", "Italian coast"),
            RoutePoint(40.8, 14.3, "Naples", "Amalfi Coast"),
            RoutePoint(37.5, 15.1, "Sicily", "Mount Etna"),
            RoutePoint(35.9, 14.5, "Malta", "Island nation"),
            RoutePoint(35.3, 25.1, "Crete", "Greek islands"),
            RoutePoint(37.9, 23.7, "Athens", "Aegean Sea"),
            RoutePoint(41.0, 29.0, "Istanbul", "Bosphorus"),
        ],
    ),
    "andes_mountains": FlyOverRoute(
        id="andes_mountains",
        name="Andes Mountains",
        description="Fly along the Andes from Patagonia to Colombia",
        points=[
            RoutePoint(-50.0, -73.0, "Patagonia", "Southern Ice Field"),
            RoutePoint(-43.0, -71.5, "Lake District", "Volcanic lakes"),
            RoutePoint(-34.0, -70.0, "Aconcagua region", "Highest peak"),
            RoutePoint(-27.1, -69.3, "Atacama", "Driest desert"),
            RoutePoint(-21.0, -68.0, "Altiplano", "High plateau"),
            RoutePoint(-16.0, -69.0, "Lake Titicaca", "Highest navigable lake"),
            RoutePoint(-13.5, -72.0, "Cusco", "Machu Picchu region"),
            RoutePoint(-9.0, -77.5, "Huascaran", "Tropical glaciers"),
            RoutePoint(-1.5, -78.5, "Ecuador", "Avenue of Volcanoes"),
            RoutePoint(4.6, -75.6, "Colombia", "Coffee region"),
            RoutePoint(7.0, -73.0, "Northern Andes", "Colombia highlands"),
        ],
    ),
    "silk_road": FlyOverRoute(
        id="silk_road",
        name="Ancient Silk Road",
        description="Trace the ancient trade route from Xi'an to Constantinople",
        points=[
            RoutePoint(34.3, 108.9, "Xi'an", "Eastern terminus"),
            RoutePoint(36.6, 101.8, "Xining", "Qinghai approach"),
            RoutePoint(39.7, 98.5, "Jiayuguan", "End of Great Wall"),
            RoutePoint(40.1, 94.7, "Dunhuang", "Mogao Caves"),
            RoutePoint(41.7, 86.2, "Turpan", "Flaming Mountains"),
            RoutePoint(39.5, 76.0, "Kashgar", "Taklamakan crossing"),
            RoutePoint(40.5, 72.8, "Fergana Valley", "Uzbekistan"),
            RoutePoint(39.7, 66.9, "Samarkand", "Timurid capital"),
            RoutePoint(37.6, 61.8, "Merv", "Turkmenistan"),
            RoutePoint(35.7, 51.4, "Tehran", "Persian plateau"),
            RoutePoint(33.3, 44.4, "Baghdad", "Mesopotamia"),
            RoutePoint(36.2, 36.2, "Aleppo", "Syrian crossing"),
            RoutePoint(41.0, 29.0, "Constantinople", "Western terminus"),
        ],
    ),
    "pacific_ring_of_fire": FlyOverRoute(
        id="pacific_ring_of_fire",
        name="Pacific Ring of Fire",
        description="Circle the Pacific along the volcanic ring of fire",
        points=[
            RoutePoint(-41.3, 174.8, "New Zealand", "Taupo Volcanic Zone"),
            RoutePoint(-22.3, 166.5, "New Caledonia", "Coral Sea"),
            RoutePoint(-6.0, 145.8, "Papua New Guinea", "Volcanic highlands"),
            RoutePoint(7.5, 126.0, "Philippines", "Mindanao volcanoes"),
            RoutePoint(31.3, 130.7, "Japan", "Sakurajima volcano"),
            RoutePoint(35.4, 138.7, "Mount Fuji", "Iconic stratovolcano"),
            RoutePoint(52.3, 158.3, "Kamchatka", "Russian volcanoes"),
            RoutePoint(54.8, -163.4, "Aleutian Islands", "Volcanic chain"),
            RoutePoint(60.5, -152.4, "Alaska", "Mount Redoubt"),
            RoutePoint(46.2, -122.2, "Mount St. Helens", "Cascade Range"),
            RoutePoint(19.4, -155.3, "Hawaii", "Kilauea"),
            RoutePoint(-0.8, -91.1, "Galapagos", "Shield volcanoes"),
            RoutePoint(-33.4, -70.6, "Santiago", "Andean volcanoes"),
        ],
    ),
    "great_barrier_reef": FlyOverRoute(
        id="great_barrier_reef",
        name="Great Barrier Reef",
        description="Fly along Australia's Great Barrier Reef from north to south",
        points=[
            RoutePoint(-10.7, 142.5, "Torres Strait", "Northern tip"),
            RoutePoint(-12.5, 143.8, "Cape York coast", "Remote reefs"),
            RoutePoint(-14.7, 145.5, "Cooktown reefs", "Ribbon reefs"),
            RoutePoint(-16.9, 146.2, "Cairns", "Outer reef"),
            RoutePoint(-18.3, 147.0, "Townsville reefs", "Central section"),
            RoutePoint(-19.8, 149.2, "Whitsunday Islands", "Heart Reef"),
            RoutePoint(-20.7, 150.0, "Mackay reefs", "Southern section"),
            RoutePoint(-23.2, 151.8, "Gladstone", "Southern terminus"),
        ],
    ),
}


class FlyOverManager:
    """
    Manages location-aware and fly-over wallpaper modes.
    
    Location-aware: detects user location via IP and shows nearby imagery.
    Fly-over: advances along a route with each wallpaper change.
    """

    def __init__(self, registry: SourceRegistry):
        self._registry = registry
        self._enabled = False
        self._mode = "location"  # "location" or "flyover"
        self._current_route_id: Optional[str] = None
        self._route_position: int = 0
        self._user_latitude: Optional[float] = None
        self._user_longitude: Optional[float] = None
        self._state_file = Path.home() / ".config" / "earthview" / "flyover_state.json"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value in ("location", "flyover"):
            self._mode = value

    @property
    def available_routes(self) -> dict:
        """Get all available fly-over routes."""
        return {rid: r for rid, r in ROUTES.items()}

    @property
    def current_route(self) -> Optional[FlyOverRoute]:
        """Get the currently active route."""
        if self._current_route_id:
            return ROUTES.get(self._current_route_id)
        return None

    @property
    def route_progress(self) -> Tuple[int, int]:
        """Get current position and total points in active route."""
        route = self.current_route
        if route:
            return self._route_position, route.total_points
        return 0, 0

    def set_route(self, route_id: str) -> bool:
        """Set the active fly-over route."""
        if route_id in ROUTES:
            self._current_route_id = route_id
            self._route_position = 0
            self._save_state()
            return True
        return False

    def detect_location(self) -> Tuple[Optional[float], Optional[float]]:
        """Detect user location via IP geolocation."""
        try:
            # Use free IP geolocation service
            response = requests.get("http://ip-api.com/json/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    self._user_latitude = data.get("lat")
                    self._user_longitude = data.get("lon")
                    return self._user_latitude, self._user_longitude
        except Exception as e:
            print(f"Location detection failed: {e}")

        return None, None

    def fetch_appropriate(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """
        Fetch an image based on current mode.
        
        Location mode: fetches imagery near user's detected location.
        Fly-over mode: fetches imagery at the current route point.
        """
        if not self._enabled:
            return self._registry.fetch_random(source_id)

        if self._mode == "location":
            return self._fetch_location_based(source_id)
        elif self._mode == "flyover":
            return self._fetch_flyover(source_id)

        return self._registry.fetch_random(source_id)

    def _fetch_location_based(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch imagery near the user's location."""
        lat, lon = self._user_latitude, self._user_longitude

        # Detect if not already known
        if lat is None or lon is None:
            lat, lon = self.detect_location()

        if lat is not None and lon is not None:
            result = self._registry.fetch_near_location(lat, lon, 1000, source_id)
            if result:
                return result

        # Fallback to random
        return self._registry.fetch_random(source_id)

    def _fetch_flyover(self, source_id: Optional[str] = None) -> Optional[ImageResult]:
        """Fetch imagery at the current fly-over route point, then advance."""
        route = self.current_route
        if not route or not route.points:
            return self._registry.fetch_random(source_id)

        # Get current point
        point = route.points[self._route_position % route.total_points]

        # Try to fetch near this location
        result = self._registry.fetch_near_location(
            point.latitude, point.longitude, 500, source_id
        )

        # Advance position for next call
        self._route_position = (self._route_position + 1) % route.total_points
        self._save_state()

        if result:
            # Enrich with route context
            if not result.title or result.title.startswith("Earth View"):
                result.title = f"{route.name}: {point.name}"
            result.description = (
                f"Fly-over {route.name} - {point.name}: {point.description}. "
                f"({self._route_position}/{route.total_points})"
            )
            return result

        # Fallback to random
        return self._registry.fetch_random(source_id)

    def _save_state(self) -> None:
        """Save fly-over state to disk."""
        state = {
            "route_id": self._current_route_id,
            "position": self._route_position,
            "user_lat": self._user_latitude,
            "user_lon": self._user_longitude,
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, 'w') as f:
                json.dump(state, f)
        except IOError:
            pass

    def load_state(self) -> None:
        """Load fly-over state from disk."""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r') as f:
                    state = json.load(f)
                self._current_route_id = state.get("route_id")
                self._route_position = state.get("position", 0)
                self._user_latitude = state.get("user_lat")
                self._user_longitude = state.get("user_lon")
        except (IOError, json.JSONDecodeError):
            pass

    def get_config(self) -> dict:
        """Get current configuration."""
        return {
            "enabled": self._enabled,
            "mode": self._mode,
            "route_id": self._current_route_id,
            "position": self._route_position,
        }

    def load_config(self, config: dict) -> None:
        """Load configuration from dict."""
        self._enabled = config.get("enabled", False)
        self._mode = config.get("mode", "location")
        self._current_route_id = config.get("route_id")
        self._route_position = config.get("position", 0)
