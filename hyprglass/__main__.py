"""The stable command interface used by configuration files and services."""
import importlib
import os
import runpy
import sys

from hyprglass.paths import BASE

MODULES = {
    'wifi': ('wifi.menu', []),
    'bluetooth': ('bluetooth.menu', []),
    'notes': ('notes.cli', []),
    'widgets': ('assistant.app', []),
    'assistant': ('assistant.app', ['assistant']),
    'calendar': ('assistant.app', ['calendar']),
    'panel': ('assistant.app', ['panel']),
    'wallpapers': ('assistant.app', ['wallpapers']),
    'restore-wallpapers': ('wallpapers.restore', []),
    'record': ('capture.record', []),
    'date': ('waybar.date', []),
    'sidebar-config': ('sidebar.config', []),
    'sidebar-style': ('sidebar.style', []),
    'build-metadata': ('sidebar.native.metadata', []),
    'verify': ('verify', []),
}
SHELL = {
    'sidebar': 'sidebar/start.sh',
    'notifications': 'sidebar/client.sh',
    'quicksettings': 'sidebar/quicksettings.sh',
    'launcher': 'launcher/start.sh',
    'files': 'files/start.sh',
    'ollama': 'assistant/ollama.sh',
    'build-sidebar': 'sidebar/native/build.sh',
    'desktop': 'desktop/start.sh',
}


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments or arguments[0] in ('-h', '--help'):
        print('Usage: hypr-glass COMMAND [ARGUMENTS]')
        print('Commands: ' + ', '.join(sorted([*MODULES, *SHELL, 'setup', 'check'])))
        return 0
    command, *arguments = arguments
    if command == 'setup':
        return importlib.import_module('hyprglass.install.setup').main(arguments)
    if command == 'check':
        return importlib.import_module('hyprglass.install.setup').main(['--check', *arguments])
    if command in SHELL:
        script = BASE / 'hyprglass' / SHELL[command]
        os.execv(str(script), [str(script), *arguments])
    if command not in MODULES:
        print('Unknown command: ' + command, file=sys.stderr)
        return 2
    module, prefix = MODULES[command]
    sys.argv = [str(BASE / 'hyprglass' / (module.replace('.', '/') + '.py')), *prefix, *arguments]
    runpy.run_module('hyprglass.' + module, run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
