#!/usr/bin/env python3
import signal
import gi
import json
import os
import random
import requests
import subprocess
import threading
import time
import shutil
from pathlib import Path

# Ensure correct GTK versions
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk as gtk
from gi.repository import GLib
from gi.repository import AyatanaAppIndicator3 as appindicator
from gi.repository import Notify as notify

APPINDICATOR_ID = 'earthview-wallpaper'
APP_NAME = 'Earth View Wallpaper Changer'
# Cache timeout in seconds (1 hour)
CACHE_TIMEOUT = 3600

class EarthViewApp:
    def __init__(self):
        self.script_dir = Path(__file__).parent.absolute()
        self.wallpaper_path = self.script_dir / "wallpaper.jpg"
        self.data_path = self.script_dir / "data.json"
        self.logo_path = self.script_dir / "logo.png"
        self.data = None
        self.is_changing = False
        
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
        
        # Load data
        self.load_data()

    def load_data(self):
        """Load image data from JSON file"""
        try:
            with open(self.data_path, 'r') as file:
                self.data = json.load(file)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.show_notification(f"Error loading data: {str(e)}", "error")
            self.data = []

    def build_menu(self):
        """Build the indicator menu"""
        menu = gtk.Menu()
        
        # Change wallpaper item
        item_change = gtk.MenuItem(label='Change Wallpaper')
        item_change.connect('activate', self.on_change_wallpaper)
        menu.append(item_change)
        
        # Separator
        menu.append(gtk.SeparatorMenuItem())
        
        # Autostart toggle
        item_autostart = gtk.CheckMenuItem(label='Start automatically at login')
        autostart_file = Path.home() / ".config" / "autostart" / "earthview-wallpaper.desktop"
        item_autostart.set_active(autostart_file.exists())
        item_autostart.connect('toggled', self.toggle_autostart)
        menu.append(item_autostart)
        
        # Separator
        menu.append(gtk.SeparatorMenuItem())
        
        # About item
        item_about = gtk.MenuItem(label='About')
        item_about.connect('activate', self.on_about)
        menu.append(item_about)
        
        # Quit item
        item_quit = gtk.MenuItem(label='Quit')
        item_quit.connect('activate', self.on_quit)
        menu.append(item_quit)
        
        menu.show_all()
        return menu

    def toggle_autostart(self, widget):
        """Toggle autostart setting"""
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_file = autostart_dir / "earthview-wallpaper.desktop"
        
        # Check if we're installed as a package or running from source
        desktop_file = Path("/usr/share/applications/earthview-wallpaper.desktop")
        if not desktop_file.exists():
            # Running from source, create a custom desktop file
            if not autostart_dir.exists():
                autostart_dir.mkdir(parents=True, exist_ok=True)
                
            if widget.get_active():
                # Create autostart file
                script_path = Path(__file__).absolute()
                with open(autostart_file, 'w') as f:
                    f.write(f"""[Desktop Entry]
Name=Earth View Wallpaper
Comment=Change your desktop wallpaper to beautiful Google Earth images
Exec={script_path}
Icon={self.logo_path}
Terminal=false
Type=Application
Categories=Utility;Graphics;
StartupNotify=true
X-GNOME-Autostart-enabled=true
""")
            else:
                # Remove autostart file
                if autostart_file.exists():
                    autostart_file.unlink()
        else:
            # Installed as package
            if not autostart_dir.exists():
                autostart_dir.mkdir(parents=True, exist_ok=True)
                
            if widget.get_active():
                # Enable autostart
                if not autostart_file.exists():
                    shutil.copy(desktop_file, autostart_file)
                    with open(autostart_file, 'a') as f:
                        f.write("\nX-GNOME-Autostart-enabled=true\n")
            else:
                # Disable autostart
                if autostart_file.exists():
                    autostart_file.unlink()

    def on_change_wallpaper(self, _):
        """Handle wallpaper change request"""
        if self.is_changing:
            self.show_notification("Already changing wallpaper, please wait...", "info")
            return
            
        if not self.data:
            self.show_notification("No wallpaper data available", "error")
            return
            
        # Use threading to prevent UI freezing
        thread = threading.Thread(target=self.change_wallpaper_thread)
        thread.daemon = True
        thread.start()

    def change_wallpaper_thread(self):
        """Change wallpaper in a separate thread"""
        self.is_changing = True
        try:
            # Select random image
            rand_index = random.randint(0, len(self.data) - 1)
            image_data = self.data[rand_index]
            
            # Get image URL - handle both formats in data
            if "image" in image_data:
                wallpaper_url = image_data["image"]
            elif "Image URL" in image_data:
                wallpaper_url = "http://" + image_data["Image URL"]
            else:
                raise ValueError("Invalid image data format")
                
            # Ensure URL starts with http or https
            if not wallpaper_url.startswith(('http://', 'https://')):
                wallpaper_url = "https://" + wallpaper_url
                
            # Download image
            response = requests.get(wallpaper_url, timeout=10)
            response.raise_for_status()
            
            with open(self.wallpaper_path, 'wb') as file:
                file.write(response.content)
                
            # Set as wallpaper (both for older and newer GNOME versions)
            location = f"file://{self.wallpaper_path}"
            
            # For GNOME 42+ (Ubuntu 22.04+)
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background", 
                           "picture-uri-dark", location], check=False)
            
            # For all GNOME versions
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background", 
                           "picture-uri", location], check=True)
            
            # Show success notification on the main thread
            GLib.idle_add(self.show_notification, "Wallpaper changed successfully", "success")
            
        except Exception as e:
            GLib.idle_add(self.show_notification, f"Error changing wallpaper: {str(e)}", "error")
        finally:
            self.is_changing = False

    def show_notification(self, message, level="info"):
        """Show a notification with appropriate icon"""
        icons = {
            "success": "dialog-information",
            "error": "dialog-error",
            "info": "dialog-information"
        }
        icon = icons.get(level, "dialog-information")
        notify.Notification.new(APP_NAME, message, icon).show()

    def on_about(self, _):
        """Show about dialog"""
        about_dialog = gtk.AboutDialog()
        about_dialog.set_program_name(APP_NAME)
        about_dialog.set_version("1.0")
        about_dialog.set_copyright("Earth View by Google")
        about_dialog.set_comments("Changes your desktop wallpaper to beautiful satellite images from Google Earth")
        about_dialog.set_website("https://earthview.withgoogle.com")
        about_dialog.set_logo(gtk.Image.new_from_file(str(self.logo_path)).get_pixbuf())
        about_dialog.run()
        about_dialog.destroy()

    def on_quit(self, _):
        """Quit the application"""
        notify.uninit()
        gtk.main_quit()

def main():
    app = EarthViewApp()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    gtk.main()

if __name__ == "__main__":
    main()
