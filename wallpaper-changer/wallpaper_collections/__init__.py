"""
Wallpaper Collections - curated themed sets of wallpaper images.

Collections are JSON files in this directory, each containing a themed
set of image entries that can be used across sources.
"""

from .manager import CollectionManager, Collection

__all__ = ['CollectionManager', 'Collection']
