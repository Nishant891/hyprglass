"""The desktop's Arch packages, command checks, and minimum native versions."""
import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


COMMANDS = {
    'Hyprland': 'hyprland', 'hyprctl': 'hyprland', 'waybar': 'waybar',
    'wofi': 'wofi', 'rofi': 'rofi', 'hyprpaper': 'hyprpaper', 'hyprlock': 'hyprlock',
    'systemctl': 'systemd', 'dbus-send': 'dbus', 'nmcli': 'networkmanager',
    'bluetoothctl': 'bluez-utils', 'rfkill': 'util-linux', 'wpctl': 'wireplumber',
    'pipewire': 'pipewire', 'pipewire-pulse': 'pipewire-pulse',
    'brightnessctl': 'brightnessctl', 'notify-send': 'libnotify', 'curl': 'curl',
    'flock': 'util-linux', 'getent': 'glibc', 'nautilus': 'nautilus',
    'playerctl': 'playerctl', 'wf-recorder': 'wf-recorder', 'hyprshot': 'hyprshot',
    'grim': 'grim', 'slurp': 'slurp', 'wl-copy': 'wl-clipboard', 'file': 'file',
}
BUILD_TOOLS = {
    'git': 'git', 'cc': 'base-devel', 'meson': 'meson', 'ninja': 'ninja',
    'valac': 'vala', 'blueprint-compiler': 'blueprint-compiler', 'sassc': 'sassc',
    'pkg-config': 'pkgconf', 'glib-compile-resources': 'glib2',
    'glib-compile-schemas': 'glib2',
}
LIBRARIES = {
    'gtk4': ('4.16.13', 'gtk4'), 'gtk4-layer-shell-0': ('1.0.4', 'gtk4-layer-shell'),
    'glib-2.0': ('2.82', 'glib2'), 'libadwaita-1': ('1.6.1', 'libadwaita'),
    'granite-7': ('7.5.0', 'granite7'), 'gee-0.8': ('0.20.6', 'libgee'),
    'wayland-client': ('1.23', 'wayland'), 'json-glib-1.0': ('1.6', 'json-glib'),
    'libpulse': (None, 'libpulse'), 'libpulse-mainloop-glib': (None, 'libpulse'),
    'gio-unix-2.0': (None, 'glib2'),
}
TERMINALS = ('ghostty', 'kitty', 'foot', 'alacritty', 'wezterm', 'konsole', 'xterm')
RUNTIME_PACKAGES = ('python', 'python-gobject', 'python-dbus', 'gtk4',
                    'gtk4-layer-shell', 'gdk-pixbuf2', 'bluez', 'adwaita-fonts',
                    'ttf-jetbrains-mono-nerd')


@dataclass(frozen=True)
class Issue:
    message: str
    packages: tuple[str, ...]


def version(text):
    match = re.search(r'(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?', text)
    if not match:
        raise ValueError('Could not parse version from ' + repr(text.strip()[:160]))
    return tuple(int(part or 0) for part in match.groups())


def run(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=15)


def is_arch():
    try:
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines()
                       if '=' in line and not line.startswith('#'))
    except OSError:
        return False
    identities = ' '.join(release.get(key, '').strip('"\'') for key in ('ID', 'ID_LIKE'))
    return 'arch' in identities.split()


def packages(terminal, build):
    required = set(COMMANDS.values()) | set(RUNTIME_PACKAGES)
    if terminal in TERMINALS:
        required.add(terminal)
    if build:
        required.update(BUILD_TOOLS.values())
        required.update(package for _, package in LIBRARIES.values())
    return sorted(required)


def unsatisfied_packages(terminal, build):
    result = run(['pacman', '-T', *packages(terminal, build)])
    if result.returncode not in (0, 127):
        raise ValueError('Could not inspect Arch dependencies: ' + result.stderr.strip())
    return sorted(result.stdout.splitlines())


def inspect(terminal=None, build=False):
    issues = []
    if sys.version_info < (3, 11):
        issues.append(Issue('Python >= 3.11 is required; upgrade your Python package.', ('python',)))
    for command, package in {**COMMANDS, **(BUILD_TOOLS if build else {})}.items():
        if not shutil.which(command):
            issues.append(Issue('Missing command ' + command, (package,)))
    if terminal and not shutil.which(terminal):
        issues.append(Issue('Missing terminal ' + terminal,
                            (terminal,) if terminal in TERMINALS else ()))
    for module, package in (('gi', 'python-gobject'), ('dbus', 'python-dbus')):
        if importlib.util.find_spec(module) is None:
            issues.append(Issue('Missing Python module ' + module, (package,)))
    if shutil.which('Hyprland'):
        try:
            result = run(['Hyprland', '--version'])
            if result.returncode:
                raise ValueError('Hyprland --version failed: ' + result.stderr.strip())
            actual = version(result.stdout)
            if actual < (0, 55, 0):
                issues.append(Issue('Hyprland >= 0.55 is required for Lua configuration; found '
                                    + '.'.join(map(str, actual)), ('hyprland',)))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            issues.append(Issue(str(error), ('hyprland',)))
    try:
        script = ('import gi,json; gi.require_version("Gtk","4.0"); '
                  'gi.require_version("Gtk4LayerShell","1.0"); '
                  'gi.require_version("GdkPixbuf","2.0"); '
                  'from gi.repository import Gtk,Gtk4LayerShell,GdkPixbuf; '
                  'print(json.dumps([Gtk.get_major_version(),Gtk.get_minor_version(),'
                  'Gtk.get_micro_version()]))')
        result = run([sys.executable, '-c', script])
        if result.returncode:
            raise ValueError('GTK introspection unavailable: ' + result.stderr.strip().splitlines()[-1])
        actual = json.loads(result.stdout)
        if not isinstance(actual, list) or len(actual) != 3 or any(type(v) is not int for v in actual):
            raise ValueError('Could not parse GTK runtime version')
        if tuple(actual) < (4, 16, 13):
            issues.append(Issue('GTK >= 4.16.13 is required; found ' + '.'.join(map(str, actual)), ('gtk4',)))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        issues.append(Issue(str(error), ('python-gobject', 'gtk4', 'gtk4-layer-shell', 'gdk-pixbuf2')))
    if build and shutil.which('pkg-config'):
        for library, (minimum, package) in LIBRARIES.items():
            try:
                result = run(['pkg-config', '--modversion', library])
                if result.returncode:
                    raise ValueError('Missing development library ' + library)
                actual = version(result.stdout)
                if minimum and actual < version(minimum):
                    raise ValueError(f'{library} >= {minimum} required; found {result.stdout.strip()}')
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                issues.append(Issue(str(error), (package,)))
    if is_arch() and shutil.which('pacman'):
        try:
            for package in unsatisfied_packages(terminal, build):
                issues.append(Issue('Missing Arch dependency ' + package, (package,)))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            issues.append(Issue(str(error), ()))
    return issues


def install_packages(terminal, build):
    if not is_arch():
        raise ValueError('Automatic packages support Arch and ID_LIKE=arch only. '
                         'Install the reported prerequisites with your distribution package manager, '
                         'then run install.sh --no-packages.')
    if not shutil.which('sudo') or not shutil.which('pacman'):
        raise ValueError('Automatic installation needs sudo and pacman. Install prerequisites manually '
                         'and rerun install.sh --no-packages.')
    subprocess.run(['sudo', 'pacman', '-Syu', '--needed',
                    *unsatisfied_packages(terminal, build)], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check Hypr Glass prerequisites without changing files.')
    parser.add_argument('--terminal', choices=TERMINALS, default=None)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args(argv)
    issues = inspect(args.terminal, args.build)
    for issue in issues:
        print(issue.message)
    print('Arch packages: ' + ' '.join(packages(args.terminal, args.build)))
    print('Ollama is optional. Enable NetworkManager, Bluetooth and PipeWire services as needed.')
    return int(bool(issues))
