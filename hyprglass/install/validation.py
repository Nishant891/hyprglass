from pathlib import Path
import os
import subprocess
import tempfile

from hyprglass.paths import BASE


def verify_configuration():
    with tempfile.TemporaryDirectory(prefix='hypr-glass-check-') as temporary:
        home = Path(temporary)
        (home / '.config').mkdir()
        (home / '.config/hypr').symlink_to(BASE, target_is_directory=True)
        runtime = home / 'runtime'
        runtime.mkdir(mode=0o700)
        environment = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                           XDG_RUNTIME_DIR=str(runtime), XDG_CACHE_HOME=str(home / 'cache'),
                           XDG_STATE_HOME=str(home / 'state'), HYPRLAND_NO_SD_NOTIFY='1')
        result = subprocess.run(['Hyprland', '--verify-config', '--config', str(BASE / 'hyprland.lua')],
                                env=environment, capture_output=True, text=True, timeout=30)
        if result.returncode:
            detail = (result.stdout + result.stderr).strip()[-4000:]
            raise ValueError('Installed Hyprland rejected this configuration. Update the compatible '
                             'Hyprland provider or correct the reported settings before installing.\n' + detail)
