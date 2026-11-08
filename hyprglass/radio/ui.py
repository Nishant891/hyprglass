"""Rofi dialogs scoped to radio controls; never read or kill the app launcher."""
import fcntl
import html
import json
import os
from pathlib import Path
import subprocess

from hyprglass.paths import BASE
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
TOGGLE = object()
RADIO_ICONS = {'wifi': '󰖩', 'bluetooth': '󰂯'}

def notify(title, text):
    subprocess.run(['notify-send', '-a', title, title, html.escape(text)], check=False)

def choose(kind, title, rows=None, secret=False, message=None, powered=None):
    with (RUNTIME / f'hypr-{kind}-dialog.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        args = ['rofi', '-no-config', '-theme', str(BASE / 'hyprglass/radio/radio.rasi'),
                '-pid', str(RUNTIME / f'hypr-{kind}-rofi.pid'), '-dmenu', '-no-history',
                '-no-hover-select', '-no-cycle', '-scroll-method', '0',
                '-kb-row-up', 'Up,Control+p', '-kb-row-down', 'Down,Control+n',
                '-ml-row-up', '', '-ml-row-down', '', '-ml-row-left', '', '-ml-row-right', '',
                '-me-select-entry', 'MousePrimary', '-me-accept-entry', 'MouseDPrimary',
                '-p', RADIO_ICONS[kind] if powered is not None else display(title)]
        if rows is None:
            args += ['-theme-str', 'entry { placeholder: ""; } listview { lines: 0; }']
        else:
            args += ['-i', '-format', 'i', '-selected-row', '0',
                     '-theme-str', 'entry { placeholder: "Type to filter…"; }']
            if powered is None:
                args.append('-no-custom')
        if powered is not None:
            switch = BASE / 'hyprglass/radio' / ('toggle-on.svg' if powered else 'toggle-off.svg')
            args += ['-kb-custom-1', 'Alt+t', '-theme-str',
                     'inputbar { children: [ prompt, entry, button-toggle ]; }\n'
                     'prompt { font: "JetBrainsMono Nerd Font Propo 15"; padding: 0px 2px 0px 0px; }\n'
                     'button-toggle { background-image: url(' + json.dumps(str(switch)) + ', both); }']
        if secret:
            args.append('-password')
        if message:
            args += ['-mesg', html.escape(message)]
        result = subprocess.run(args, input='\n'.join(display(s) for s in (rows or [])),
                                capture_output=True, text=True)
        if result.returncode == 10 and powered is not None:
            return TOGGLE
        if result.returncode:
            if result.stderr.strip():
                notify(kind.title(), 'Could not open picker: ' + result.stderr.strip()[:300])
            return None
        value = result.stdout.removesuffix('\n')
        if rows is not None:
            return int(value) if value.isdigit() and int(value) < len(rows) else None
        return value

def display(text):
    return ''.join(c if c.isprintable() else ' ' for c in str(text))

def write_state(kind, **data):
    path = RUNTIME / f'hypr-{kind}-state.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data))
    tmp.replace(path)

def read_state(kind):
    try:
        return json.loads((RUNTIME / f'hypr-{kind}-state.json').read_text())
    except (OSError, ValueError):
        return {}
