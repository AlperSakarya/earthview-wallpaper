"""
Preferences Dialog for Earth View Wallpaper Engine.

Provides a GTK settings window for configuring:
- Active sources and API keys
- Auto-change interval
- Time-aware settings
- Fly-over route selection
- Collection management
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk as gtk


class PreferencesDialog(gtk.Dialog):
    """Preferences window for the wallpaper engine."""

    def __init__(self, app):
        super().__init__(
            title="Earth View Wallpaper - Preferences",
            parent=None,
            flags=0,
        )
        self.app = app
        self.set_default_size(550, 500)
        self.set_border_width(10)

        # Add close button
        self.add_button("Close", gtk.ResponseType.CLOSE)

        # Create notebook (tabs)
        notebook = gtk.Notebook()
        content = self.get_content_area()
        content.pack_start(notebook, True, True, 0)

        # Tab 1: Sources
        notebook.append_page(self._build_sources_tab(), gtk.Label(label="Sources"))

        # Tab 2: Schedule
        notebook.append_page(self._build_schedule_tab(), gtk.Label(label="Schedule"))

        # Tab 3: Modes
        notebook.append_page(self._build_modes_tab(), gtk.Label(label="Modes"))

        # Tab 4: About Sources
        notebook.append_page(self._build_info_tab(), gtk.Label(label="Info"))

        self.show_all()


    def _build_sources_tab(self) -> gtk.Box:
        """Build the sources configuration tab."""
        box = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        # Header
        label = gtk.Label()
        label.set_markup("<b>Image Sources</b>\nEnable or disable sources. "
                         "Disabled sources won't be used for random selection.")
        label.set_xalign(0)
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)

        # Sources list
        active = self.app.config.get("active_sources", [])
        all_active = len(active) == 0  # empty means all

        for source_id, source in self.app.registry.all_sources.items():
            row = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=10)

            check = gtk.CheckButton(label=source.name)
            check.set_active(all_active or source_id in active)
            check.connect('toggled', self._on_source_toggled, source_id)
            row.pack_start(check, False, False, 0)

            # Description
            desc = gtk.Label(label=source.description[:60])
            desc.set_xalign(0)
            desc.get_style_context().add_class("dim-label")
            row.pack_start(desc, True, True, 0)

            # API key entry if needed
            if source.requires_api_key:
                entry = gtk.Entry()
                entry.set_placeholder_text("API Key")
                entry.set_width_chars(20)
                current_key = self.app.config.get("source_configs", {}).get(
                    source_id, {}).get("api_key", "")
                if current_key:
                    entry.set_text(current_key)
                entry.connect('changed', self._on_api_key_changed, source_id)
                row.pack_end(entry, False, False, 0)

            box.pack_start(row, False, False, 0)

        # Unsplash special config
        box.pack_start(gtk.Separator(), False, False, 5)
        unsplash_label = gtk.Label()
        unsplash_label.set_markup(
            "<b>Unsplash Configuration</b>\n"
            "Works without API key (uses search scraping). "
            "For better access, get a free key at unsplash.com/developers")
        unsplash_label.set_xalign(0)
        unsplash_label.set_line_wrap(True)
        box.pack_start(unsplash_label, False, False, 0)

        unsplash_row = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=10)
        unsplash_entry = gtk.Entry()
        unsplash_entry.set_placeholder_text("Unsplash API Key (optional)")
        unsplash_entry.set_width_chars(40)
        current = self.app.config.get("source_configs", {}).get(
            "unsplash", {}).get("api_key", "")
        if current:
            unsplash_entry.set_text(current)
        unsplash_entry.connect('changed', self._on_api_key_changed, "unsplash")
        unsplash_row.pack_start(unsplash_entry, True, True, 0)
        box.pack_start(unsplash_row, False, False, 0)

        # NASA APOD key config
        apod_row = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=10)
        apod_label = gtk.Label(label="NASA API Key (optional, for APOD):")
        apod_row.pack_start(apod_label, False, False, 0)
        apod_entry = gtk.Entry()
        apod_entry.set_placeholder_text("DEMO_KEY")
        apod_entry.set_width_chars(30)
        current = self.app.config.get("source_configs", {}).get(
            "nasa_apod", {}).get("api_key", "")
        if current:
            apod_entry.set_text(current)
        apod_entry.connect('changed', self._on_api_key_changed, "nasa_apod")
        apod_row.pack_start(apod_entry, True, True, 0)
        box.pack_start(apod_row, False, False, 0)

        scrolled = gtk.ScrolledWindow()
        scrolled.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.AUTOMATIC)
        scrolled.add(box)
        return scrolled


    def _build_schedule_tab(self) -> gtk.Box:
        """Build the schedule/interval configuration tab."""
        box = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        label = gtk.Label()
        label.set_markup("<b>Auto-Change Schedule</b>\n"
                         "Set how often the wallpaper changes automatically.")
        label.set_xalign(0)
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)

        from indicator import INTERVAL_OPTIONS
        current = self.app.config.get("auto_change_interval", 3600)

        group = None
        for name, seconds in INTERVAL_OPTIONS.items():
            if group is None:
                radio = gtk.RadioButton(label=name)
                group = radio
            else:
                radio = gtk.RadioButton.new_with_label_from_widget(group, name)
            radio.set_active(seconds == current)
            radio.connect('toggled', self._on_interval_changed, seconds)
            box.pack_start(radio, False, False, 0)

        return box

    def _build_modes_tab(self) -> gtk.Box:
        """Build the modes (time-aware, fly-over) configuration tab."""
        box = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        # Time-aware section
        time_label = gtk.Label()
        time_label.set_markup("<b>Time-Aware Mode</b>\n"
                              "Selects wallpapers matching the time of day.\n"
                              "Sunrise (5-8), Day (8-17), Sunset (17-20), Night (20-5)")
        time_label.set_xalign(0)
        time_label.set_line_wrap(True)
        box.pack_start(time_label, False, False, 0)

        time_check = gtk.CheckButton(label="Enable time-aware wallpaper selection")
        time_check.set_active(self.app.time_aware.enabled)
        time_check.connect('toggled', self._on_time_aware_toggled)
        box.pack_start(time_check, False, False, 0)

        box.pack_start(gtk.Separator(), False, False, 10)

        # Fly-over section
        fly_label = gtk.Label()
        fly_label.set_markup("<b>Fly-Over Mode</b>\n"
                             "Location-aware shows imagery near you.\n"
                             "Fly-over follows a scenic route with each change.")
        fly_label.set_xalign(0)
        fly_label.set_line_wrap(True)
        box.pack_start(fly_label, False, False, 0)

        fly_check = gtk.CheckButton(label="Enable fly-over / location mode")
        fly_check.set_active(self.app.flyover.enabled)
        fly_check.connect('toggled', self._on_flyover_toggled)
        box.pack_start(fly_check, False, False, 0)

        # Mode selection
        mode_box = gtk.Box(orientation=gtk.Orientation.HORIZONTAL, spacing=10)
        mode_label = gtk.Label(label="Mode:")
        mode_box.pack_start(mode_label, False, False, 0)

        radio_location = gtk.RadioButton(label="Near my location")
        radio_location.set_active(self.app.flyover.mode == "location")
        radio_location.connect('toggled', self._on_flyover_mode, "location")
        mode_box.pack_start(radio_location, False, False, 0)

        radio_route = gtk.RadioButton.new_with_label_from_widget(
            radio_location, "Follow a route")
        radio_route.set_active(self.app.flyover.mode == "flyover")
        radio_route.connect('toggled', self._on_flyover_mode, "flyover")
        mode_box.pack_start(radio_route, False, False, 0)
        box.pack_start(mode_box, False, False, 0)

        # Route selection
        route_label = gtk.Label(label="Select route:")
        route_label.set_xalign(0)
        box.pack_start(route_label, False, False, 0)

        for route_id, route in self.app.flyover.available_routes.items():
            radio = gtk.RadioButton(label=f"{route.name} - {route.description[:50]}")
            if (self.app.flyover.current_route and
                    self.app.flyover.current_route.id == route_id):
                radio.set_active(True)
            radio.connect('toggled', self._on_route_selected, route_id)
            box.pack_start(radio, False, False, 0)

        scrolled = gtk.ScrolledWindow()
        scrolled.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.AUTOMATIC)
        scrolled.add(box)
        return scrolled


    def _build_info_tab(self) -> gtk.Box:
        """Build the info/about tab showing source details."""
        box = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        info_text = """<b>Available Image Sources</b>

<b>Google Earth View</b>
Curated satellite imagery from Google Earth. Over 1500 stunning landscapes 
viewed from space. No API key needed.

<b>NASA EPIC</b>
Real-time full-disc Earth photos from the DSCOVR satellite, 1 million miles 
from Earth. Updates every ~2 hours. No API key needed.

<b>Himawari-8</b>
Japanese geostationary weather satellite. Full-color true-color Earth imagery 
centered on Asia-Pacific. Updates every 10 minutes. No API key needed.

<b>GOES-16/18</b>
NOAA weather satellites showing the Americas in stunning GeoColor composite. 
Full-disc and continental views. Updates every 15 minutes. No API key needed.

<b>NASA APOD</b>
Astronomy Picture of the Day. Daily curated space and Earth imagery. 
Works with free DEMO_KEY, or get your own at api.nasa.gov.

<b>Unsplash</b>
High-quality scenery, aerial, nature, and space photography. 
Searches for fresh wallpapers automatically. Optional API key for 
better access (get free at unsplash.com/developers).

<b>Collections</b>
Themed sets: Volcanic Landscapes, River Deltas, Arctic Ice, 
Desert Abstract, Human Patterns. Add your own via the collections folder.

<b>Tips</b>
- Use "Live Satellite" for the most recent real-time imagery
- Time-aware mode picks bright images during day, dark/space at night
- Fly-over mode follows scenic routes around the world
- Add any wallpaper to Favorites to revisit later"""

        label = gtk.Label()
        label.set_markup(info_text)
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_selectable(True)
        box.pack_start(label, False, False, 0)

        scrolled = gtk.ScrolledWindow()
        scrolled.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.AUTOMATIC)
        scrolled.add(box)
        return scrolled


    # -- Callbacks --

    def _on_source_toggled(self, widget, source_id):
        """
        Add or remove a source from the lock.

        Mirrors the tray menu: an empty selection means every source is used.
        Because an empty list and a full list behave identically, unchecking
        the last remaining source reverts to using them all rather than
        leaving no usable source.
        """
        locked = list(self.app.config.get("active_sources", []))
        all_ids = list(self.app.registry.all_sources.keys())

        # An empty lock displays as every box checked. Unchecking one from that
        # state means "all except this one", so seed the list first.
        if not locked:
            locked = list(all_ids)

        if widget.get_active():
            if source_id not in locked:
                locked.append(source_id)
        else:
            locked = [s for s in locked if s != source_id]

        # Full selection is stored as no lock, keeping one canonical form.
        if set(locked) == set(all_ids):
            locked = []

        self.app.config.set("active_sources", locked)
        self.app.registry.set_active_sources(locked)

    def _on_api_key_changed(self, widget, source_id):
        """Handle API key entry change."""
        key = widget.get_text().strip()
        configs = self.app.config.get("source_configs", {})
        if source_id not in configs:
            configs[source_id] = {}
        configs[source_id]["api_key"] = key
        self.app.config.set("source_configs", configs)
        self.app.registry.set_config(source_id, configs[source_id])

    def _on_interval_changed(self, widget, seconds):
        """Handle interval radio button change."""
        if widget.get_active():
            self.app.config.set("auto_change_interval", seconds)
            self.app._auto_change_interval = seconds
            self.app._start_auto_change()

    def _on_time_aware_toggled(self, widget):
        """Handle time-aware toggle."""
        self.app.time_aware.enabled = widget.get_active()
        self.app.config.set("time_aware", self.app.time_aware.get_config())

    def _on_flyover_toggled(self, widget):
        """Handle fly-over toggle."""
        self.app.flyover.enabled = widget.get_active()
        self.app.config.set("flyover", self.app.flyover.get_config())

    def _on_flyover_mode(self, widget, mode):
        """Handle fly-over mode change."""
        if widget.get_active():
            self.app.flyover.mode = mode
            self.app.config.set("flyover", self.app.flyover.get_config())

    def _on_route_selected(self, widget, route_id):
        """Handle route selection."""
        if widget.get_active():
            self.app.flyover.set_route(route_id)
            self.app.config.set("flyover", self.app.flyover.get_config())
