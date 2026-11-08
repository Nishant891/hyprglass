#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from hyprglass.paths import BASE as base
source = base / sys.argv[1]
if (Gtk.get_major_version(), Gtk.get_minor_version()) >= (4, 24):
    print(source)
else:
    target = base / 'data/styles' / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    css = re.sub(r'backdrop-filter\s*:[^;]+;', '', source.read_text())
    css = re.sub(r'url\("(icons/[^\"]+)"\)',
                 lambda match: 'url(' + json.dumps(str(source.parent / match[1])) + ')', css)
    target.write_text(css)
    print(target)
