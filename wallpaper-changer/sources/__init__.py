"""
Earth View Wallpaper - Multi-Source Plugin System

Each source plugin provides satellite/aerial imagery from different providers.
Sources are automatically discovered and registered when placed in this directory.
"""

from .base import WallpaperSource, ImageResult
from .registry import SourceRegistry

__all__ = ['WallpaperSource', 'ImageResult', 'SourceRegistry']
