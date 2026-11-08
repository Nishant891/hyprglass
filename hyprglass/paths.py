"""Locations shared by the installed desktop and its components."""
from pathlib import Path
import os
import tempfile

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
TOOLS = BASE / 'tools'
COMMAND = BASE / 'bin/hypr-glass'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()))
