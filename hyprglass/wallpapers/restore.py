#!/usr/bin/env python3
"""Restore selected wallpapers, retaining the original defaults for new outputs."""
import subprocess
import time
from hyprglass.wallpapers.state import restore_wallpapers

for attempt in range(10):
    try:
        restore_wallpapers()
        break
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        if attempt == 9:
            raise
    time.sleep(.3)
