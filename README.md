# Earth View Wallpaper Engine v2.0

A multi-source desktop wallpaper changer that pulls stunning imagery from satellites, space, and nature photography.

## Sources

- **Google Earth View** - 1500+ curated satellite landscapes from Google Earth
- **NASA EPIC** - Real-time full-disc Earth photos from 1 million miles away (DSCOVR satellite)
- **Himawari-8** - Japanese weather satellite, full-color Earth every 10 minutes
- **GOES-16/18** - NOAA weather satellites showing the Americas in true color
- **NASA APOD** - Astronomy Picture of the Day
- **Unsplash** - High-quality scenery, aerial, nature, and space photography (searches for fresh wallpapers automatically)

## Features

- **Multi-source wallpaper engine** with plugin architecture
- **Live satellite feeds** - get the latest real-time Earth imagery
- **Time-aware mode** - picks wallpapers matching time of day (sunrise/day/sunset/night)
- **Fly-over mode** - virtual flights along scenic routes (Nile River, Mediterranean, Andes, Silk Road, Pacific Ring of Fire, Great Barrier Reef)
- **Location-aware** - shows satellite imagery near your location
- **Themed collections** - Volcanic Landscapes, River Deltas, Arctic Ice, Desert Abstract, Human Patterns
- **Favorites** - save wallpapers you love and revisit them
- **History** - browse and reuse recent wallpapers
- **Auto-change** - configurable interval from 5 minutes to 24 hours
- **Preferences dialog** - configure sources, API keys, modes, and schedules
- **System tray indicator** with full menu
- **Auto-start** at login

## Installation

### Method 1: Debian Package (Recommended)

```bash
# Single command - installs package and all dependencies automatically
sudo apt install ./earthview-wallpaper_2.0.4_all.deb
```

The package handles upgrades cleanly: it stops any running instance before
replacing files, clears stale locks, and restarts the app afterwards if it
was running. Use `apt` rather than `dpkg -i` so dependencies resolve in one
step.

To remove it:

```bash
sudo apt remove earthview-wallpaper
```

Your settings in `~/.config/earthview/` and cached wallpaper in
`~/.cache/earthview/` are left in place on removal; delete them by hand if
you want a completely clean slate.

### Method 2: Manual

```bash
# Install system dependencies
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 \
  python3-cairo python3-bs4 python3-lxml python3-requests

# Clone and run
git clone https://github.com/yourusername/earthview.git
cd earthview
chmod +x wallpaper-changer/indicator.py
./wallpaper-changer/indicator.py
```

## Usage

Launch from applications menu or terminal:
```bash
earthview-wallpaper
```

### System Tray Menu

- **Change Wallpaper** - random image from active sources
- **Change From Source** - pick a specific source
- **Live Satellite** - get the most recent image from live feeds
- **Collections** - browse themed image sets
- **Favorites** - manage and use saved wallpapers
- **Fly-Over Mode** - enable location or route-based selection
- **Time-Aware Mode** - adapt to time of day
- **Auto-Change Interval** - set timer (5min to 24h)
- **History** - revisit recent wallpapers
- **Preferences** - full configuration dialog

### Configuration

Settings are stored in `~/.config/earthview/`:
- `config.json` - sources, intervals, mode settings
- `history.json` - wallpaper change history
- `favorites.json` - saved favorites
- `recent_urls.json` - deduplication record preventing repeats within 7 days
- `collections/` - user-created collections

The currently applied wallpaper is cached at `~/.cache/earthview/wallpaper.jpg`.

### Image variety

Sources are used in strict rotation, so each one is selected in turn rather
than at random. Every applied image URL is recorded, and no image repeats
within seven days. At a 5-minute interval that means roughly 336 images per
source per week, which every source can supply.

### API Keys (Optional)

All sources work without API keys. For better access:

- **Unsplash**: Get a free key at https://unsplash.com/developers
- **NASA APOD**: Get a free key at https://api.nasa.gov

Configure keys in Preferences > Sources tab.

## Adding Custom Collections

Create a JSON file in `~/.config/earthview/collections/` or `wallpaper-changer/collections/`:

```json
{
  "id": "my_collection",
  "name": "My Collection",
  "description": "My custom wallpaper set",
  "icon": "",
  "tags": ["custom"],
  "images": [
    {
      "url": "https://example.com/image.jpg",
      "title": "My Image",
      "description": "A description",
      "category": "daytime",
      "tags": ["custom"],
      "attribution": "Credit"
    }
  ]
}
```

## Adding New Sources

Create a Python file in `wallpaper-changer/sources/`:

```python
from .base import WallpaperSource, ImageResult

class MySource(WallpaperSource):
    @property
    def name(self):
        return "My Source"

    @property
    def source_id(self):
        return "my_source"

    def fetch_random(self):
        # Return an ImageResult or None
        return ImageResult(url="...", source_name=self.name, title="...")
```

The source is automatically discovered and available in the app.

## Data Migration

If upgrading from v1.x:
```bash
python3 wallpaper-changer/migrate_data.py --input wallpaper-changer/data.json
```

## Building the Debian Package

```bash
./build-package.sh
```

This stages the source tree into the package layout, normalises ownership to
`root:root` and permissions to Debian policy, compresses the changelog and man
page, and builds `earthview-wallpaper_2.0.4_all.deb`. The result passes
`lintian` with no errors or warnings.

## Fly-Over Routes

Built-in routes for the fly-over mode:
- **Nile River** - Lake Victoria to the Mediterranean Delta
- **Mediterranean Coastline** - Gibraltar to Istanbul
- **Andes Mountains** - Patagonia to Colombia
- **Ancient Silk Road** - Xi'an to Constantinople
- **Pacific Ring of Fire** - Volcanic ring around the Pacific
- **Great Barrier Reef** - North to south along Australia's coast

## Troubleshooting

### System tray icon not showing
```bash
sudo apt install gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```
Log out and back in.

### Live satellite images not loading
Check your internet connection. NASA EPIC and GOES require access to:
- epic.gsfc.nasa.gov
- cdn.star.nesdis.noaa.gov
- himawari8.nict.go.jp

### Wallpaper not changing
```bash
gsettings get org.gnome.desktop.background picture-uri
gsettings get org.gnome.desktop.background picture-uri-dark
```

## License

MIT License
