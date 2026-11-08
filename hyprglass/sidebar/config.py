#!/usr/bin/env python3
import json
from pathlib import Path

from hyprglass.wallpapers.state import BASE, atomic_text


def create_config(base=BASE, sysfs=Path('/sys/class')):
    config = json.loads((base / 'hyprglass/sidebar/config.json').read_text())
    backlight = config.setdefault('widget-config', {}).setdefault('backlight', {})
    if not backlight.get('device') and 'backlight' in config['widgets']:
        subsystem = backlight.get('subsystem', 'backlight')
        devices = sorted((sysfs / subsystem).iterdir()) if (sysfs / subsystem).is_dir() else []
        if devices:
            backlight['device'] = devices[0].name
        else:
            config['widgets'].remove('backlight')
    target = base / 'data/sidebar.json'
    atomic_text(target, json.dumps(config, indent=2) + '\n')
    return target


if __name__ == '__main__':
    print(create_config())
