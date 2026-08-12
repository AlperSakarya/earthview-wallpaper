#!/usr/bin/env python3
"""
Earth View Wallpaper - Multi-Source Wallpaper Engine

A modern desktop wallpaper changer that pulls stunning imagery from multiple
sources including Google Earth View, NASA satellites, Unsplash, and more.

Features:
- Multiple image sources (Earth View, NASA EPIC, Himawari-8, GOES, APOD, Unsplash)
- Themed collections (volcanic, arctic, rivers, deserts, human patterns)
- Time-aware mode (adapts to time of day)
- Fly-over mode (virtual flights along scenic routes)
- Favorites and wallpaper history
- Configurable auto-change interval
- Source selection and preferences
"""

import signal
import gi
import json
import os
import random
import requests
import subprocess
import threading
import time
import sys
from pathlib import Path
from datetime import datetime

# Ensure correct GTK versions
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk as gtk
from gi.repository import GLib
from gi.repository import AyatanaAppIndicator3 as appindicator
from gi.repository import Notify as notify

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sources import SourceRegistry, ImageResult
from sources.base import ImageCategory
from wallpaper_collections.manager import CollectionManager
from timeaware import TimeAwareManager
from flyover import FlyOverManager
from logsetup import setup_logging, get_logger, log_path

log = get_logger()


APPINDICATOR_ID = 'earthview-wallpaper'
APP_NAME = 'Earth View Wallpaper'
VERSION = '2.0.6'

# Default auto-change interval options (in seconds)
INTERVAL_OPTIONS = {
    "Off": 0,
    "5 minutes": 300,
    "15 minutes": 900,
    "30 minutes": 1800,
    "1 hour": 3600,
    "2 hours": 7200,
    "6 hours": 21600,
    "12 hours": 43200,
    "24 hours": 86400,
}


class Config:
    """Application configuration manager."""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "earthview"
        self.config_file = self.config_dir / "config.json"
        self.history_file = self.config_dir / "history.json"
        self.favorites_file = self.config_dir / "favorites.json"
        self._ensure_dirs()
        self._data = self._load()

    def _ensure_dirs(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._defaults()

    def _defaults(self) -> dict:
        return {
            "active_sources": [],  # empty = all
            "auto_change_interval": 3600,
            "time_aware": {"enabled": False},
            "flyover": {"enabled": False, "mode": "location"},
            "source_configs": {},
            "active_collection": None,
            "last_source": None,
        }

    def save(self):
        with open(self.config_file, 'w') as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()



class History:
    """Wallpaper history tracker."""

    MAX_HISTORY = 100

    def __init__(self, config: Config):
        self._file = config.history_file
        self._entries: list = self._load()

    def _load(self) -> list:
        if self._file.exists():
            try:
                with open(self._file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save(self):
        with open(self._file, 'w') as f:
            json.dump(self._entries[-self.MAX_HISTORY:], f, indent=2)

    def add(self, image: ImageResult):
        entry = {
            "url": image.url,
            "title": image.title,
            "source": image.source_name,
            "timestamp": datetime.now().isoformat(),
            "attribution": image.attribution,
        }
        self._entries.append(entry)
        if len(self._entries) > self.MAX_HISTORY:
            self._entries = self._entries[-self.MAX_HISTORY:]
        self._save()

    @property
    def recent(self) -> list:
        """Get last 10 entries."""
        return list(reversed(self._entries[-10:]))

    @property
    def last(self) -> dict:
        return self._entries[-1] if self._entries else {}

    def clear(self):
        self._entries = []
        self._save()


class Favorites:
    """Manages user's favorite wallpapers."""

    def __init__(self, config: Config):
        self._file = config.favorites_file
        self._entries: list = self._load()

    def _load(self) -> list:
        if self._file.exists():
            try:
                with open(self._file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save(self):
        with open(self._file, 'w') as f:
            json.dump(self._entries, f, indent=2)

    def add(self, image: ImageResult):
        # Avoid duplicates
        if any(e["url"] == image.url for e in self._entries):
            return
        entry = {
            "url": image.url,
            "title": image.title,
            "source": image.source_name,
            "attribution": image.attribution,
            "added": datetime.now().isoformat(),
        }
        self._entries.append(entry)
        self._save()

    def remove(self, url: str):
        self._entries = [e for e in self._entries if e["url"] != url]
        self._save()

    def is_favorite(self, url: str) -> bool:
        return any(e["url"] == url for e in self._entries)

    @property
    def all(self) -> list:
        return list(self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    def get_random(self) -> dict:
        if self._entries:
            return random.choice(self._entries)
        return {}



class EarthViewApp:
    """Main application class."""

    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        # The downloaded wallpaper is per-user runtime data, so it must live in
        # the user's cache directory. Writing next to the code breaks when the
        # app is installed system-wide under root-owned /usr/share.
        self.cache_dir = Path(
            os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
        ) / "earthview"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.wallpaper_path = self.cache_dir / "wallpaper.jpg"
        self.logo_path = self.script_dir / "logo.png"

        # Config and state
        self.config = Config()
        self.history = History(self.config)
        self.favorites = Favorites(self.config)

        # Source registry
        self.registry = SourceRegistry()
        self._apply_source_configs()
        self.registry.discover_sources()

        # Collections
        collections_dir = self.script_dir / "wallpaper_collections"
        self.collections = CollectionManager(collections_dir)

        # Time-aware manager
        self.time_aware = TimeAwareManager(self.registry)
        self.time_aware.load_config(self.config.get("time_aware", {}))

        # Fly-over manager
        self.flyover = FlyOverManager(self.registry)
        self.flyover.load_config(self.config.get("flyover", {}))
        self.flyover.load_state()

        # State
        self.is_changing = False
        self.current_image: ImageResult = None
        self._auto_change_timer = None
        self._auto_change_interval = self.config.get("auto_change_interval", 3600)

        # Initialize notification system
        notify.init(APPINDICATOR_ID)

        # Setup indicator
        self.indicator = appindicator.Indicator.new(
            APPINDICATOR_ID,
            str(self.logo_path),
            appindicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

        # Start auto-change timer if configured
        self._start_auto_change()

        log.info("started: %d sources, %d collections, interval=%ss, "
                 "time_aware=%s, flyover=%s/%s",
                 len(self.registry.all_sources),
                 len(self.collections.all_collections),
                 self._auto_change_interval,
                 self.time_aware.enabled,
                 self.flyover.enabled, self.flyover.mode)
        log.debug("sources: %s", ", ".join(self.registry.all_sources))
        self._repair_stale_wallpaper()

    def _repair_stale_wallpaper(self):
        """
        Repair a wallpaper setting that points at a file which no longer exists.

        Versions up to 2.0.2 saved the wallpaper inside the installation
        directory. That file is removed on upgrade, which leaves the desktop
        pointing at a missing path and rendering black. Detect that and apply
        a fresh wallpaper instead.
        """
        stale = False
        for key in ("picture-uri", "picture-uri-dark"):
            try:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.background", key],
                    capture_output=True, text=True, timeout=10)
                value = result.stdout.strip().strip("'\"")
                if not value.startswith("file://"):
                    continue
                path = Path(value[len("file://"):])
                if not path.exists():
                    log.warning("%s points at missing file: %s", key, path)
                    stale = True
            except Exception as e:
                log.debug("could not inspect %s: %s", key, e)

        if not stale:
            return

        # Reapply the cached image if we have one, otherwise fetch a new one.
        if self.wallpaper_path.exists():
            log.info("repairing stale wallpaper setting using cached image")
            location = f"file://{self.wallpaper_path}"
            for key in ("picture-uri", "picture-uri-dark"):
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.background",
                     key, location],
                    check=False, capture_output=True)
        else:
            log.info("repairing stale wallpaper setting by fetching a new image")
            thread = threading.Thread(target=self._change_wallpaper_thread)
            thread.daemon = True
            thread.start()

    def _apply_source_configs(self):
        """Apply saved source configurations (API keys, etc.)."""
        configs = self.config.get("source_configs", {})
        for source_id, cfg in configs.items():
            self.registry.set_config(source_id, cfg)

        active = self.config.get("active_sources", [])
        if active:
            self.registry.set_active_sources(active)


    def build_menu(self):
        """Build the indicator menu."""
        menu = gtk.Menu()

        # -- Change Wallpaper --
        item_change = gtk.MenuItem(label='Change Wallpaper')
        item_change.connect('activate', self.on_change_wallpaper)
        menu.append(item_change)

        # -- Change from specific source submenu --
        item_sources = gtk.MenuItem(label='Change From Source')
        submenu_sources = gtk.Menu()
        for source_id, source in self.registry.all_sources.items():
            item = gtk.MenuItem(label=source.name)
            item.connect('activate', self.on_change_from_source, source_id)
            submenu_sources.append(item)
        item_sources.set_submenu(submenu_sources)
        menu.append(item_sources)

        # -- Live Satellite submenu --
        item_live = gtk.MenuItem(label='Live Satellite')
        submenu_live = gtk.Menu()
        for source_id, source in self.registry.all_sources.items():
            if source.supports_live:
                item = gtk.MenuItem(label=f"{source.name} (Latest)")
                item.connect('activate', self.on_fetch_latest, source_id)
                submenu_live.append(item)
        item_live.set_submenu(submenu_live)
        menu.append(item_live)

        menu.append(gtk.SeparatorMenuItem())

        # -- Collections submenu --
        item_collections = gtk.MenuItem(label='Collections')
        submenu_collections = gtk.Menu()
        for cid, collection in self.collections.all_collections.items():
            label = f"{collection.name} ({collection.count})"
            item = gtk.MenuItem(label=label)
            item.connect('activate', self.on_collection_random, cid)
            submenu_collections.append(item)
        item_collections.set_submenu(submenu_collections)
        menu.append(item_collections)

        # -- Favorites --
        item_fav_menu = gtk.MenuItem(label=f'Favorites ({self.favorites.count})')
        submenu_fav = gtk.Menu()
        item_add_fav = gtk.MenuItem(label='Add Current to Favorites')
        item_add_fav.connect('activate', self.on_add_favorite)
        submenu_fav.append(item_add_fav)
        item_random_fav = gtk.MenuItem(label='Random from Favorites')
        item_random_fav.connect('activate', self.on_random_favorite)
        submenu_fav.append(item_random_fav)
        submenu_fav.append(gtk.SeparatorMenuItem())
        # Show recent favorites
        for fav in self.favorites.all[:5]:
            title = fav.get("title", "Untitled")[:40]
            item = gtk.MenuItem(label=title)
            item.connect('activate', self.on_set_specific_url, fav["url"])
            submenu_fav.append(item)
        item_fav_menu.set_submenu(submenu_fav)
        menu.append(item_fav_menu)

        menu.append(gtk.SeparatorMenuItem())


        # -- Fly-Over mode submenu --
        item_flyover = gtk.MenuItem(label='Fly-Over Mode')
        submenu_flyover = gtk.Menu()

        item_flyover_enable = gtk.CheckMenuItem(label='Enable Fly-Over')
        item_flyover_enable.set_active(self.flyover.enabled)
        item_flyover_enable.connect('toggled', self.on_toggle_flyover)
        submenu_flyover.append(item_flyover_enable)

        item_location_mode = gtk.RadioMenuItem(label='Location-Aware (near me)')
        item_location_mode.set_active(self.flyover.mode == "location")
        item_location_mode.connect('toggled', self.on_set_flyover_mode, "location")
        submenu_flyover.append(item_location_mode)

        item_route_mode = gtk.RadioMenuItem.new_with_label_from_widget(
            item_location_mode, 'Fly-Over Route')
        item_route_mode.set_active(self.flyover.mode == "flyover")
        item_route_mode.connect('toggled', self.on_set_flyover_mode, "flyover")
        submenu_flyover.append(item_route_mode)

        submenu_flyover.append(gtk.SeparatorMenuItem())

        # Route selection
        for route_id, route in self.flyover.available_routes.items():
            pos, total = self.flyover.route_progress
            label = route.name
            if self.flyover.current_route and route_id == self.flyover.current_route.id:
                label += f" [{pos}/{total}]"
            item = gtk.MenuItem(label=label)
            item.connect('activate', self.on_select_route, route_id)
            submenu_flyover.append(item)

        item_flyover.set_submenu(submenu_flyover)
        menu.append(item_flyover)

        # -- Time-Aware mode --
        item_time = gtk.CheckMenuItem(label='Time-Aware Mode')
        item_time.set_active(self.time_aware.enabled)
        item_time.connect('toggled', self.on_toggle_time_aware)
        menu.append(item_time)

        # Show current time category
        if self.time_aware.enabled:
            cat_name = self.time_aware.get_category_name()
            item_cat = gtk.MenuItem(label=f'  Current: {cat_name}')
            item_cat.set_sensitive(False)
            menu.append(item_cat)

        menu.append(gtk.SeparatorMenuItem())

        # -- Auto-change interval --
        item_interval = gtk.MenuItem(label='Auto-Change Interval')
        submenu_interval = gtk.Menu()
        current_interval = self._auto_change_interval
        group = None
        for label, seconds in INTERVAL_OPTIONS.items():
            if group is None:
                item = gtk.RadioMenuItem(label=label)
                group = item
            else:
                item = gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            item.set_active(seconds == current_interval)
            item.connect('toggled', self.on_set_interval, seconds)
            submenu_interval.append(item)
        item_interval.set_submenu(submenu_interval)
        menu.append(item_interval)

        menu.append(gtk.SeparatorMenuItem())


        # -- History submenu --
        item_history = gtk.MenuItem(label='History')
        submenu_history = gtk.Menu()
        for entry in self.history.recent:
            title = entry.get("title", "Untitled")[:40]
            source = entry.get("source", "")
            ts = entry.get("timestamp", "")[:16]
            label = f"{title} ({source}) - {ts}"
            item = gtk.MenuItem(label=label)
            item.connect('activate', self.on_set_specific_url, entry["url"])
            submenu_history.append(item)
        if not self.history.recent:
            item_empty = gtk.MenuItem(label='No history yet')
            item_empty.set_sensitive(False)
            submenu_history.append(item_empty)
        submenu_history.append(gtk.SeparatorMenuItem())
        item_clear_hist = gtk.MenuItem(label='Clear History')
        item_clear_hist.connect('activate', self.on_clear_history)
        submenu_history.append(item_clear_hist)
        item_history.set_submenu(submenu_history)
        menu.append(item_history)

        # -- Current wallpaper info --
        if self.current_image:
            item_info = gtk.MenuItem(
                label=f'Current: {self.current_image.title[:50]}')
            item_info.set_sensitive(False)
            menu.append(item_info)
            if self.current_image.attribution:
                item_attr = gtk.MenuItem(
                    label=f'  {self.current_image.attribution[:60]}')
                item_attr.set_sensitive(False)
                menu.append(item_attr)

        menu.append(gtk.SeparatorMenuItem())

        # -- Autostart --
        item_autostart = gtk.CheckMenuItem(label='Start at login')
        autostart_file = Path.home() / ".config" / "autostart" / "earthview-wallpaper.desktop"
        item_autostart.set_active(autostart_file.exists())
        item_autostart.connect('toggled', self.toggle_autostart)
        menu.append(item_autostart)

        # -- Preferences --
        item_prefs = gtk.MenuItem(label='Preferences')
        item_prefs.connect('activate', self.on_preferences)
        menu.append(item_prefs)

        # -- View log --
        item_log = gtk.MenuItem(label='View Log')
        item_log.connect('activate', self.on_view_log)
        menu.append(item_log)

        menu.append(gtk.SeparatorMenuItem())

        # -- About --
        item_about = gtk.MenuItem(label='About')
        item_about.connect('activate', self.on_about)
        menu.append(item_about)

        # -- Quit --
        item_quit = gtk.MenuItem(label='Quit')
        item_quit.connect('activate', self.on_quit)
        menu.append(item_quit)

        menu.show_all()
        return menu

    def _refresh_menu(self):
        """Rebuild the menu to reflect current state."""
        self.indicator.set_menu(self.build_menu())


    # -- Event handlers --

    def on_change_wallpaper(self, _):
        """Change wallpaper using current mode settings."""
        if self.is_changing:
            self.show_notification("Already changing wallpaper, please wait...")
            return
        thread = threading.Thread(target=self._change_wallpaper_thread)
        thread.daemon = True
        thread.start()

    def on_change_from_source(self, _, source_id):
        """Change wallpaper from a specific source."""
        if self.is_changing:
            return
        thread = threading.Thread(
            target=self._change_wallpaper_thread, args=(source_id,))
        thread.daemon = True
        thread.start()

    def on_fetch_latest(self, _, source_id):
        """Fetch latest live satellite image."""
        if self.is_changing:
            return
        thread = threading.Thread(
            target=self._fetch_latest_thread, args=(source_id,))
        thread.daemon = True
        thread.start()

    def on_collection_random(self, _, collection_id):
        """Set wallpaper from a collection."""
        if self.is_changing:
            return
        thread = threading.Thread(
            target=self._collection_wallpaper_thread, args=(collection_id,))
        thread.daemon = True
        thread.start()

    def on_add_favorite(self, _):
        """Add current wallpaper to favorites."""
        if self.current_image:
            self.favorites.add(self.current_image)
            self.show_notification(f"Added to favorites: {self.current_image.title[:40]}")
            GLib.idle_add(self._refresh_menu)
        else:
            self.show_notification("No current wallpaper to favorite")

    def on_random_favorite(self, _):
        """Set a random favorite as wallpaper."""
        fav = self.favorites.get_random()
        if fav:
            thread = threading.Thread(
                target=self._set_url_thread, args=(fav["url"], fav.get("title", "")))
            thread.daemon = True
            thread.start()
        else:
            self.show_notification("No favorites yet")

    def on_set_specific_url(self, _, url):
        """Set a specific URL as wallpaper (from history/favorites)."""
        thread = threading.Thread(
            target=self._set_url_thread, args=(url, ""))
        thread.daemon = True
        thread.start()

    def on_toggle_flyover(self, widget):
        """Toggle fly-over mode."""
        self.flyover.enabled = widget.get_active()
        self.config.set("flyover", self.flyover.get_config())

    def on_set_flyover_mode(self, widget, mode):
        """Set fly-over mode type."""
        if widget.get_active():
            self.flyover.mode = mode
            self.config.set("flyover", self.flyover.get_config())

    def on_select_route(self, _, route_id):
        """Select a fly-over route."""
        self.flyover.set_route(route_id)
        self.flyover.mode = "flyover"
        self.flyover.enabled = True
        self.config.set("flyover", self.flyover.get_config())
        route = self.flyover.current_route
        if route:
            self.show_notification(f"Fly-over: {route.name}\n{route.description}")
        GLib.idle_add(self._refresh_menu)

    def on_toggle_time_aware(self, widget):
        """Toggle time-aware mode."""
        self.time_aware.enabled = widget.get_active()
        self.config.set("time_aware", self.time_aware.get_config())
        if widget.get_active():
            cat = self.time_aware.get_category_name()
            self.show_notification(f"Time-aware mode on - Current period: {cat}")
        GLib.idle_add(self._refresh_menu)

    def on_set_interval(self, widget, seconds):
        """Set auto-change interval."""
        if widget.get_active():
            self._auto_change_interval = seconds
            self.config.set("auto_change_interval", seconds)
            self._start_auto_change()

    def on_clear_history(self, _):
        """Clear wallpaper history."""
        self.history.clear()
        GLib.idle_add(self._refresh_menu)


    def on_preferences(self, _):
        """Open preferences dialog."""
        from preferences import PreferencesDialog
        dialog = PreferencesDialog(self)
        dialog.run()
        dialog.destroy()
        # Reload config after prefs change
        self._apply_source_configs()
        GLib.idle_add(self._refresh_menu)

    def on_view_log(self, _):
        """Open the log file in the user's default text viewer."""
        path = log_path()
        if not path.exists():
            self.show_notification("No log file yet")
            return
        try:
            subprocess.Popen(["xdg-open", str(path)],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception as e:
            log.warning("could not open log viewer: %s", e)
            self.show_notification(f"Log file: {path}")

    def on_about(self, _):
        """Show about dialog."""
        about = gtk.AboutDialog()
        about.set_program_name(APP_NAME)
        about.set_version(VERSION)
        about.set_copyright("Earth View Wallpaper Engine")
        about.set_comments(
            "Multi-source wallpaper changer with satellite imagery from "
            "Google Earth View, NASA, Himawari-8, GOES, and Unsplash.\n\n"
            "Features: Live satellite feeds, fly-over routes, "
            "time-aware mode, collections, and more."
        )
        about.set_website("https://earthview.withgoogle.com")
        about.set_authors([
            "Earth View Wallpaper Contributors",
        ])
        about.set_license_type(gtk.License.MIT_X11)
        try:
            about.set_logo(
                gtk.Image.new_from_file(str(self.logo_path)).get_pixbuf())
        except Exception:
            pass
        about.run()
        about.destroy()

    def on_quit(self, _):
        """Quit the application."""
        self.config.save()
        notify.uninit()
        gtk.main_quit()


    # -- Wallpaper change logic --

    def _change_wallpaper_thread(self, source_id=None):
        """Main wallpaper change logic - respects current mode."""
        self.is_changing = True
        try:
            image = None

            # Priority: Fly-over > Time-aware > Random
            if self.flyover.enabled:
                mode = f"flyover/{self.flyover.mode}"
                image = self.flyover.fetch_appropriate(source_id)
            elif self.time_aware.enabled:
                mode = f"time-aware/{self.time_aware.get_category_name()}"
                image = self.time_aware.fetch_appropriate(source_id)
            else:
                mode = "rotation"
                image = self.registry.fetch_random(source_id)

            log.info("change requested (mode=%s, source=%s)",
                     mode, source_id or "auto")

            if image:
                self._apply_wallpaper(image)
            else:
                log.error("no image available (mode=%s, source=%s)",
                          mode, source_id or "auto")
                GLib.idle_add(
                    self.show_notification,
                    "No wallpaper available from selected source")
        except Exception as e:
            log.exception("wallpaper change failed")
            GLib.idle_add(
                self.show_notification,
                f"Error: {str(e)[:80]}")
        finally:
            self.is_changing = False

    def _fetch_latest_thread(self, source_id):
        """Fetch latest live satellite image."""
        self.is_changing = True
        try:
            image = self.registry.fetch_latest(source_id)
            if image:
                self._apply_wallpaper(image)
            else:
                GLib.idle_add(
                    self.show_notification,
                    "No live image available")
        except Exception as e:
            GLib.idle_add(
                self.show_notification,
                f"Error: {str(e)[:80]}")
        finally:
            self.is_changing = False

    def _collection_wallpaper_thread(self, collection_id):
        """Set wallpaper from a collection."""
        self.is_changing = True
        try:
            image = self.collections.fetch_random(collection_id)
            if image:
                self._apply_wallpaper(image)
            else:
                GLib.idle_add(
                    self.show_notification,
                    "Collection is empty")
        except Exception as e:
            GLib.idle_add(
                self.show_notification,
                f"Error: {str(e)[:80]}")
        finally:
            self.is_changing = False

    def _set_url_thread(self, url, title=""):
        """Download and set a specific URL as wallpaper."""
        self.is_changing = True
        try:
            self._download_and_set(url)
            # Create a minimal ImageResult for tracking
            image = ImageResult(
                url=url,
                source_name="Direct",
                title=title or "Wallpaper",
            )
            self.current_image = image
            self.history.add(image)
            GLib.idle_add(self.show_notification, "Wallpaper changed")
            GLib.idle_add(self._refresh_menu)
        except Exception as e:
            GLib.idle_add(
                self.show_notification,
                f"Error: {str(e)[:80]}")
        finally:
            self.is_changing = False


    def _apply_wallpaper(self, image: ImageResult):
        """Download image and set as wallpaper."""
        self._download_and_set(image.url)
        self.current_image = image
        self.history.add(image)

        # Build notification message
        msg = image.title or "Wallpaper changed"
        if image.source_name:
            msg += f"\nSource: {image.source_name}"
        if image.location_str and image.location_str != "Unknown location":
            msg += f"\nLocation: {image.location_str}"

        GLib.idle_add(self.show_notification, msg)
        GLib.idle_add(self._refresh_menu)

    def _download_and_set(self, url: str):
        """Download an image and set it as the desktop wallpaper."""
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        log.info("downloading %s", url)

        # Download
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        written = 0
        with open(self.wallpaper_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                written += len(chunk)

        content_type = response.headers.get("content-type", "unknown")
        log.info("saved %d bytes (%s) to %s",
                 written, content_type, self.wallpaper_path)

        # A truncated or error-page response would leave an unusable file and
        # the desktop would render black, so refuse to apply it.
        if written < 1024:
            raise IOError(
                f"downloaded file is too small ({written} bytes, {content_type}) "
                f"- refusing to apply")

        # Set wallpaper via gsettings
        location = f"file://{self.wallpaper_path}"

        # Both keys must be set. GNOME 42+ uses picture-uri-dark when the
        # system is in dark mode; leaving it stale shows the old (or missing)
        # image instead of the new one.
        for key in ("picture-uri", "picture-uri-dark"):
            result = subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.background",
                 key, location],
                capture_output=True, text=True)
            if result.returncode != 0:
                log.warning("gsettings %s failed: %s",
                            key, result.stderr.strip())
            else:
                log.debug("gsettings %s set", key)

        # Set scaling mode to zoom (fills screen)
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background",
             "picture-options", "zoom"],
            check=False, capture_output=True)


    # -- Auto-change timer --

    def _start_auto_change(self):
        """Start or restart the auto-change timer."""
        # Cancel existing timer
        if self._auto_change_timer:
            GLib.source_remove(self._auto_change_timer)
            self._auto_change_timer = None

        if self._auto_change_interval > 0:
            # Convert seconds to milliseconds for GLib timeout
            self._auto_change_timer = GLib.timeout_add_seconds(
                self._auto_change_interval, self._auto_change_tick)

    def _auto_change_tick(self) -> bool:
        """Called by the auto-change timer."""
        if not self.is_changing:
            thread = threading.Thread(target=self._change_wallpaper_thread)
            thread.daemon = True
            thread.start()
        return True  # Return True to keep the timer running

    # -- Autostart --

    def toggle_autostart(self, widget):
        """Toggle autostart setting."""
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_file = autostart_dir / "earthview-wallpaper.desktop"

        desktop_file = Path("/usr/share/applications/earthview-wallpaper.desktop")

        if widget.get_active():
            autostart_dir.mkdir(parents=True, exist_ok=True)
            if desktop_file.exists():
                import shutil
                shutil.copy(desktop_file, autostart_file)
                with open(autostart_file, 'a') as f:
                    f.write("\nX-GNOME-Autostart-enabled=true\n")
            else:
                script_path = Path(__file__).absolute()
                with open(autostart_file, 'w') as f:
                    f.write(f"""[Desktop Entry]
Name=Earth View Wallpaper
Comment=Multi-source wallpaper changer with satellite imagery
Exec={script_path}
Icon={self.logo_path}
Terminal=false
Type=Application
Categories=Utility;Graphics;
StartupNotify=true
X-GNOME-Autostart-enabled=true
""")
        else:
            if autostart_file.exists():
                autostart_file.unlink()

    # -- Notifications --

    def show_notification(self, message, level="info"):
        """Show a desktop notification."""
        icons = {
            "success": "dialog-information",
            "error": "dialog-error",
            "info": "dialog-information",
        }
        icon = icons.get(level, "dialog-information")
        try:
            notify.Notification.new(APP_NAME, message, icon).show()
        except Exception:
            pass


def acquire_lock():
    """Ensure only one instance runs at a time using a lock file."""
    import fcntl
    lock_file = Path.home() / ".config" / "earthview" / "earthview.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Open (or create) the lock file
    lock_fd = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write our PID
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd  # Keep reference alive to hold the lock
    except IOError:
        print("Earth View Wallpaper is already running.")
        sys.exit(0)


def main():
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Earth View Wallpaper %s starting (pid %d)", VERSION, os.getpid())
    logger.debug("python %s", sys.version.split()[0])
    logger.debug("log file: %s", log_path())

    lock = acquire_lock()
    try:
        app = EarthViewApp()
    except Exception:
        logger.exception("failed to start")
        raise
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    gtk.main()
    logger.info("exited")


if __name__ == "__main__":
    main()
