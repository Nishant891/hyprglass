"""Hyprpaper selection, startup restore, and matching Hyprlock backgrounds."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from hyprglass.paths import BASE
DIRECTORY = Path.home() / 'Pictures/Wallpaper'
FALLBACK = BASE / 'hyprglass/wallpapers/default.png'
DATA = BASE / 'data'
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.jxl', '.bmp'}

def images(directory=None):
    directory = Path(directory) if directory is not None else DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    found = sorted((path.resolve() for path in directory.iterdir()
                   if path.is_file() and path.suffix.lower() in EXTENSIONS),
                  key=lambda path: path.name.casefold())
    if not found:
        target = directory / 'default.png'
        try:
            with target.open('xb') as output, FALLBACK.open('rb') as source:
                shutil.copyfileobj(source, output)
        except FileExistsError:
            pass
        found = [target.resolve()]
    return found

def active_wallpapers():
    result = subprocess.run(['hyprctl', 'hyprpaper', 'listactive'],
                            capture_output=True, text=True, timeout=3, check=True)
    active = {}
    for line in result.stdout.splitlines():
        monitor, separator, filename = line.partition(': ')
        if separator and Path(filename).is_file():
            active[monitor] = Path(filename).resolve()
    return active

def saved_wallpapers():
    try:
        saved = json.loads((DATA / 'wallpapers.json').read_text())
        return {monitor: Path(filename).resolve() for monitor, filename in saved.items()
                if isinstance(monitor, str) and isinstance(filename, str) and Path(filename).is_file()}
    except (OSError, ValueError, AttributeError):
        return {}

def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.' + path.name,
                                         delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

@contextmanager
def selection_lock():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    with (runtime / 'hypr-wallpaper.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def image_link(image):
    image = Path(image).resolve(strict=True)
    directory = DATA / 'wallpaper-links'
    directory.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(os.fsencode(image)).hexdigest()[:24] + image.suffix.lower()
    link = directory / name
    if not link.is_symlink() or link.resolve() != image:
        link.symlink_to(image)
    return link

def sync_lock_backgrounds(active=None, fallback=None):
    active = active_wallpapers() if active is None else active
    fallback = fallback or next(iter(active.values()), FALLBACK)
    private_profile = DATA / 'private/lock/profile.jpeg'
    profile = image_link(private_profile if private_profile.is_file() else BASE / 'hyprglass/wallpapers/avatar.png')
    blocks = []
    links = {profile}
    for monitor, image in [('', fallback), *active.items()]:
        if any(character in monitor for character in '\n\r#{}='):
            raise ValueError('Invalid monitor name')
        link = image_link(image)
        links.add(link)
        blocks.append('background {\n    monitor = ' + monitor + '\n    path = ' + str(link) +
                      '\n    blur_passes = 3\n    blur_size = 8\n    contrast = 0.8916' +
                      '\n    brightness = 0.8172\n    vibrancy = 0.1696\n    vibrancy_darkness = 0.0\n}\n')
    atomic_text(DATA / 'lock-wallpapers.conf', '$profile = ' + str(profile) + '\n\n' + '\n'.join(blocks))
    for image in saved_wallpapers().values():
        links.add(image_link(image))
    for link in (DATA / 'wallpaper-links').iterdir():
        if link.is_symlink() and link not in links and re.fullmatch(r'[0-9a-f]{24}\.[a-z]+', link.name):
            link.unlink()

def set_wallpaper(monitor, image):
    link = image_link(image)
    if any(character in monitor for character in ',\n\r'):
        raise ValueError('Invalid monitor name')
    result = subprocess.run(['hyprctl', 'hyprpaper', 'wallpaper', f'{monitor},{link},cover'],
                            capture_output=True, text=True, timeout=8)
    if result.returncode or result.stdout.lstrip().lower().startswith(('error', 'invalid', 'failed')):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Hyprpaper did not apply the wallpaper.')
    if active_wallpapers().get(monitor) != Path(image).resolve():
        raise RuntimeError('Hyprpaper did not confirm the selected wallpaper.')

def apply_wallpaper(monitor, image):
    image = Path(image).resolve(strict=True)
    if image.suffix.lower() not in EXTENSIONS:
        raise ValueError('Choose an image file.')
    with selection_lock():
        set_wallpaper(monitor, image)
        saved = saved_wallpapers()
        saved.pop(monitor, None)
        saved[monitor] = image
        saved = dict(list(saved.items())[-16:])
        atomic_text(DATA / 'wallpapers.json', json.dumps({key: str(value) for key, value in saved.items()}, indent=2) + '\n')
        active = active_wallpapers()
        active[monitor] = image
        sync_lock_backgrounds(active, fallback=image)

def restore_wallpapers():
    choices = images()
    default = DIRECTORY / 'default.png'
    if default not in choices:
        default = FALLBACK
    monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors'], text=True, timeout=3))
    with selection_lock():
        saved = saved_wallpapers()
        active = {}
        for monitor in monitors:
            name = monitor['name']
            image = saved.get(name, default)
            set_wallpaper(name, image)
            active[name] = image
        sync_lock_backgrounds(active)
