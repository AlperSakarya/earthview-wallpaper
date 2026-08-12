"""
Logging setup for Earth View Wallpaper.

Writes to a rotating log file so failures can be inspected after the fact,
and mirrors to stderr when run from a terminal.

Log location:
    ~/.cache/earthview/earthview.log        (current)
    ~/.cache/earthview/earthview.log.1..3   (rotated)

Verbosity:
    Default is INFO. Enable DEBUG with either
        earthview-wallpaper --debug
    or
        EARTHVIEW_DEBUG=1 earthview-wallpaper
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "earthview"
MAX_BYTES = 1024 * 1024      # 1 MB per file
BACKUP_COUNT = 3             # keep 3 rotations

_configured = False


def log_dir() -> Path:
    """Directory holding the log files."""
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "earthview"


def log_path() -> Path:
    """Full path to the current log file."""
    return log_dir() / "earthview.log"


def debug_enabled() -> bool:
    """Whether debug verbosity was requested via flag or environment."""
    if os.environ.get("EARTHVIEW_DEBUG", "").strip() not in ("", "0", "false"):
        return True
    return "--debug" in sys.argv or "-d" in sys.argv


def setup_logging(force_debug: bool = False) -> logging.Logger:
    """
    Configure the application logger. Safe to call more than once.

    Returns the configured logger.
    """
    global _configured
    logger = logging.getLogger(LOGGER_NAME)

    if _configured:
        return logger

    level = logging.DEBUG if (force_debug or debug_enabled()) else logging.INFO
    logger.setLevel(logging.DEBUG)   # handlers filter; capture everything here
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler. If the log cannot be opened (read-only home, full disk),
    # carry on with stderr only rather than preventing startup.
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path(), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        print(f"earthview: cannot open log file: {exc}", file=sys.stderr)

    # Console handler, so running from a terminal shows the same detail.
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    _configured = True
    return logger


def get_logger(suffix: str = "") -> logging.Logger:
    """
    Get a child logger, e.g. get_logger("registry") -> "earthview.registry".

    Callers can use this at import time; configuration happens in setup_logging.
    """
    if suffix:
        return logging.getLogger(f"{LOGGER_NAME}.{suffix}")
    return logging.getLogger(LOGGER_NAME)
