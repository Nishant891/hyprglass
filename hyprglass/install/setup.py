"""Install one checkout without merging or overwriting personal configuration."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from hyprglass.paths import BASE
from hyprglass.install import backups, dependencies, settings
from hyprglass.install.validation import verify_configuration


EXECUTABLE = re.compile(r'[A-Za-z0-9_.+-]+\Z')
ARTIFACTS = ('bin/swaync', 'bin/swaync-client', 'style.css', 'schemas/gschemas.compiled')


def sources(config):
    return {
        config / 'hypr': BASE,
        config / 'ghostty': BASE / 'hyprglass/terminal/ghostty',
        config / 'systemd/user/swaync.service': BASE / 'hyprglass/sidebar/swaync.service',
        config / 'systemd/user/hypr-widgets.service': BASE / 'hyprglass/assistant/hypr-widgets.service',
        config / 'systemd/user/hypr-ollama.service': BASE / 'hyprglass/assistant/hypr-ollama.service',
        BASE / 'local.lua': None,
    }


def build_is_current():
    destination = BASE / 'tools/swaync'
    if any(not (destination / name).is_file() for name in ARTIFACTS):
        return False
    try:
        saved = json.loads((destination / 'build-metadata.json').read_text())
        result = subprocess.run(['bash', str(BASE / 'hyprglass/sidebar/native/build.sh'), '--print-metadata'],
                                capture_output=True, text=True, check=True, timeout=20)
        current = json.loads(result.stdout)
        return (isinstance(saved, dict) and set(saved) == {'source', 'inputs', 'libraries'}
                and saved == current)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def choose_terminal(requested, local):
    text = local.read_text() if local.exists() else None
    field, opening = settings.terminal_field(text) if text is not None else (None, None)
    existing = field.value if field else None
    if requested == 'auto':
        selected = existing if existing and EXECUTABLE.fullmatch(existing) and shutil.which(existing) else next(
            (name for name in dependencies.TERMINALS if shutil.which(name)), 'ghostty')
    else:
        if not EXECUTABLE.fullmatch(requested):
            raise ValueError('Use a simple executable name for --terminal, such as kitty.')
        selected = requested
    if not shutil.which(selected) and selected not in dependencies.TERMINALS:
        raise ValueError(f'Terminal {selected} is unavailable and has no automatic package mapping. '
                         'Install it first or select --terminal ghostty, kitty, foot, alacritty, '
                         'wezterm, konsole or xterm.')
    if text is None:
        text = (BASE / 'local.example.lua').read_text()
        field, opening = settings.terminal_field(text)
    elif existing == selected:
        return selected, None, None
    message = None
    if requested == 'auto' and existing and existing != selected:
        message = f'Terminal {existing} is unavailable. Set terminal to {selected}; preserve other local.lua settings.'
    if field:
        text = text[:field.start + 1] + selected + text[field.end - 1:]
    else:
        text = text[:opening] + '\n    terminal = ' + json.dumps(selected) + ',' + text[opening:]
    return selected, text, message


def link_changes(config, terminal):
    allowed = sources(config)
    target = config / 'hypr'
    if target.resolve() != BASE.resolve() and BASE.resolve().is_relative_to(target.resolve()):
        raise ValueError('Move this checkout outside ~/.config/hypr before installing it.')
    changes = []
    for target, source in allowed.items():
        if source is None or (target == config / 'ghostty' and terminal != 'ghostty'):
            continue
        if not source.exists():
            raise ValueError('Checkout is incomplete. Missing ' + str(source))
        if target.resolve() == source.resolve():
            continue
        changes.append(backups.Change(target, source=source))
    return changes


def report(terminal, build, issues, changes, root, message):
    print('Terminal: ' + terminal)
    if message:
        print(message)
    print('Native sidebar: ' + ('rebuild required' if build else 'current source and libraries match build metadata'))
    for issue in issues:
        print('Prerequisite: ' + issue.message)
    if dependencies.is_arch():
        if issues:
            missing = dependencies.unsatisfied_packages(terminal, True)
            print('Arch package command: sudo pacman -Syu --needed ' + ' '.join(missing))
        else:
            print('Package action: none. Required commands and checked versions are available.')
    else:
        print('Arch package reference: ' + ' '.join(dependencies.packages(terminal, build)))
        print('This distribution needs manual prerequisites; automatic packages support Arch and ID_LIKE=arch only.')
    for change in changes:
        action = 'link ' + str(change.source) if change.source else 'write terminal setting'
        original = 'backup existing entry' if os.path.lexists(change.target) else 'no original entry'
        print(f'Configuration: {change.target} -> {action}; {original}')
    print('Backups: ' + str(root / '<UTC timestamp-random>'))
    print('Ollama is optional. Package additions are retained after restore.')
    print('Setup reloads user unit definitions. It does not start desktop or system services.')


def execute(args):
    config = Path.home() / '.config'
    if Path(os.environ.get('XDG_CONFIG_HOME', str(config))).expanduser() != config:
        raise ValueError('Hypr Glass uses ~/.config/hypr. Custom XDG_CONFIG_HOME is unsupported. '
                         'Unset it or set it to ' + str(config) + ' before running setup.')
    root = config / 'hypr-backup'
    if args.list_backups:
        entries = backups.list_backups(root)
        print('\n'.join(name + '  ' + state for name, state in entries) or 'No Hypr Glass backups.')
        return 0
    if args.restore:
        path = backups.select_backup(root, args.restore)
        try:
            backups.restore(path, sources(config))
            subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ValueError(str(error) + '\nBackup retained at ' + str(path)) from error
        print('Restored configuration. Backup manifest retained at ' + str(path))
        print('Package additions remain installed.')
        return 0
    terminal, content, message = choose_terminal(args.terminal, BASE / 'local.lua')
    build = args.rebuild or not build_is_current()
    issues = dependencies.inspect(terminal, build)
    if not issues:
        verify_configuration()
    changes = link_changes(config, terminal)
    if content is not None:
        changes.insert(0, backups.Change(BASE / 'local.lua', content=content))
    if args.check or args.plan:
        report(terminal, build, issues, changes, root, message)
        return int(bool(issues)) if args.check else 0
    if os.geteuid() == 0:
        raise ValueError('Run setup as your desktop user, without sudo. Setup asks sudo only for pacman.')
    if issues:
        report(terminal, build, issues, changes, root, message)
        if args.no_packages:
            raise ValueError('Prerequisites are missing. Install the packages above manually, '
                             'or rerun install.sh without --no-packages on Arch Linux.')
        print('Install desktop prerequisites. Pacman will ask for confirmation.')
        dependencies.install_packages(terminal, True)
        build = args.rebuild or not build_is_current()
        issues = dependencies.inspect(terminal, build)
        if issues:
            raise ValueError('Prerequisites still fail after package installation:\n' + '\n'.join(
                issue.message for issue in issues) + '\nNo configuration links were changed.')
        verify_configuration()
    if build:
        subprocess.run(['bash', str(BASE / 'hyprglass/sidebar/native/build.sh')], check=True)
        if not build_is_current():
            raise ValueError('Native build finished without matching build metadata. No configuration links changed.')
    from hyprglass.wallpapers.state import images, sync_lock_backgrounds
    images()
    sync_lock_backgrounds({})
    transaction = backups.Transaction(root, changes, sources(config)) if changes else None
    backup = None
    try:
        backup = transaction.apply() if transaction else None
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if backup:
            try:
                backups.restore(backup, sources(config))
                subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False, capture_output=True)
            except (OSError, ValueError, subprocess.SubprocessError) as restore_error:
                raise ValueError(f'{error}\nRollback needs attention: {restore_error}\nBackup: {backup}') from error
        location = backup or (transaction.path if transaction else None)
        raise ValueError(str(error) + ('\nConfiguration backup: ' + str(location) if location else '')) from error
    if message:
        print(message)
    print('Installed. Log in to Hyprland to start the desktop.')
    print('Personal settings: ' + str(BASE / 'local.lua'))
    if backup:
        print('Configuration backup: ' + str(backup))
        print('Restore with bin/hypr-glass setup --restore ' + backup.name)
    else:
        print('Configuration links and terminal setting already match. No backup needed.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install Hypr Glass for the current desktop user.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Report all prerequisites without changing files')
    modes.add_argument('--plan', action='store_true', help='Show packages, links and backups without changing files')
    modes.add_argument('--list-backups', action='store_true')
    modes.add_argument('--restore', metavar='ID_OR_PATH')
    parser.add_argument('--terminal', default='auto', metavar='EXECUTABLE',
                        help='Preserve available local.lua terminal, else try ghostty, kitty, foot, '
                             'alacritty, wezterm, konsole, xterm; default auto')
    parser.add_argument('--no-packages', action='store_true', help='Require all prerequisites already installed')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild native sidebar regardless of metadata')
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Setup failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
