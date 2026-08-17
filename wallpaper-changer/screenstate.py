"""
Screen state detection.

Used to avoid sending desktop notifications when the display is off or the
session is locked. A notification delivered to a blanked monitor can wake it,
which is exactly what a wallpaper changer should not do while the machine is
sitting idle.

Every check fails open: if the state cannot be determined, it reports that the
screen is on, so notifications are never lost to a faulty probe.
"""

import subprocess
import time
from typing import Optional

try:
    from logsetup import get_logger
    log = get_logger("screenstate")
except ImportError:
    import logging
    log = logging.getLogger("earthview.screenstate")


# Probes are cheap but not free, and notifications can arrive in bursts, so
# results are reused briefly.
CACHE_SECONDS = 5


class ScreenState:
    """Reports whether the display is currently showing anything."""

    def __init__(self):
        self._cached: Optional[bool] = None
        self._cached_at: float = 0.0

    @staticmethod
    def _run(cmd: list, timeout: float = 3.0) -> Optional[str]:
        """Run a command, returning stdout or None on any failure."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=timeout)
            if result.returncode != 0:
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def monitor_is_off(self) -> bool:
        """
        Whether the monitor is in a DPMS power saving state.

        Relies on xset, so this only reports meaningfully on X11. Under
        Wayland it returns False and the lock check carries the decision.
        """
        output = self._run(["xset", "-q"])
        if not output:
            return False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("Monitor is"):
                # "Monitor is On" | "Off" | "Standby" | "Suspend"
                return not stripped.endswith("On")
        return False

    def session_is_locked(self) -> bool:
        """Whether the screensaver or lock screen is active."""
        output = self._run([
            "gdbus", "call", "--session",
            "--dest", "org.gnome.ScreenSaver",
            "--object-path", "/org/gnome/ScreenSaver",
            "--method", "org.gnome.ScreenSaver.GetActive",
        ])
        if not output:
            return False
        return "true" in output.lower()

    def idle_seconds(self) -> Optional[float]:
        """Seconds since the last input, or None when unavailable."""
        output = self._run([
            "gdbus", "call", "--session",
            "--dest", "org.gnome.Mutter.IdleMonitor",
            "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
            "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime",
        ])
        if not output:
            return None
        # Formatted as "(uint64 224,)", in milliseconds.
        digits = "".join(c for c in output if c.isdigit())
        if not digits:
            return None
        try:
            return int(digits) / 1000.0
        except ValueError:
            return None

    def is_visible(self, use_cache: bool = True) -> bool:
        """
        Whether anything sent to the screen would actually be seen.

        False when the monitor is powered down or the session is locked.
        """
        now = time.time()
        if (use_cache and self._cached is not None
                and now - self._cached_at < CACHE_SECONDS):
            return self._cached

        visible = True
        if self.monitor_is_off():
            log.debug("monitor is powered down")
            visible = False
        elif self.session_is_locked():
            log.debug("session is locked")
            visible = False

        self._cached = visible
        self._cached_at = now
        return visible

    def describe(self) -> str:
        """Human readable state, for logging and diagnostics."""
        parts = []
        parts.append("monitor off" if self.monitor_is_off() else "monitor on")
        if self.session_is_locked():
            parts.append("locked")
        idle = self.idle_seconds()
        if idle is not None:
            parts.append(f"idle {idle:.0f}s")
        return ", ".join(parts)
