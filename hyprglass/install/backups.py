"""No-clobber configuration transactions with a durable restore manifest."""
from contextlib import contextmanager
import ctypes
import fcntl
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat


@dataclass(frozen=True)
class Change:
    target: Path
    source: Path | None = None
    content: str | None = None


@contextmanager
def operation_lock(root):
    with directory(root, create=True) as descriptor:
        fd = os.open('.operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        with os.fdopen(fd, 'a+b') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Another installation or restore is running. Retry after it finishes.') from None
            yield


@contextmanager
def directory(path, create=False):
    """Open each component separately so symlink parents cannot redirect writes."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected an absolute path without ..: ' + str(path))
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def entry_stat(descriptor, name):
    try:
        return os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode] if value else None


def move(source_fd, source, target_fd, target):
    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, 'renameat2'):
        raise OSError('Linux renameat2 is required for safe no-clobber backups.')
    if libc.renameat2(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1):
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), target)
    os.fsync(source_fd)
    os.fsync(target_fd)


def digest(descriptor, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
    with os.fdopen(fd, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def installed(descriptor, record):
    name = Path(record['target']).name
    value = entry_stat(descriptor, name)
    if record['kind'] == 'link':
        return bool(value and stat.S_ISLNK(value.st_mode)
                    and os.readlink(name, dir_fd=descriptor) == record['expected'])
    return bool(value and stat.S_ISREG(value.st_mode) and digest(descriptor, name) == record['expected'])


def save(descriptor, manifest):
    temporary = '.manifest-' + secrets.token_hex(6)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
    with os.fdopen(fd, 'w') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, 'manifest.json', src_dir_fd=descriptor, dst_dir_fd=descriptor)
    os.fsync(descriptor)


def read(descriptor):
    fd = os.open('manifest.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
    with os.fdopen(fd) as stream:
        return json.load(stream)


def select_backup(root, identifier):
    root = Path(root)
    candidate = Path(identifier).expanduser()
    if not candidate.is_absolute():
        if len(candidate.parts) != 1 or candidate.name in ('.', '..'):
            raise ValueError('Use a backup ID or its absolute directory path.')
        candidate = root / candidate
    if candidate.parent != root or candidate.name in ('.', '..'):
        raise ValueError('Backup must be directly inside ' + str(root))
    return candidate


def list_backups(root):
    if not os.path.lexists(root):
        return []
    result = []
    with directory(root) as descriptor:
        for name in sorted(os.listdir(descriptor)):
            candidate = Path(root) / name
            value = entry_stat(descriptor, name)
            if not stat.S_ISDIR(value.st_mode):
                continue
            try:
                with directory(candidate) as child:
                    manifest = read(child)
                if not isinstance(manifest, dict):
                    raise ValueError('Invalid manifest')
                result.append((name, manifest.get('state', 'unknown')))
            except (OSError, ValueError):
                result.append((name, 'unreadable manifest'))
    return result


def validate(manifest, allowed):
    if not isinstance(manifest, dict) or manifest.get('version') != 1 \
            or not isinstance(manifest.get('entries'), list) \
            or manifest.get('state') not in ('installing', 'installed', 'restoring', 'restored'):
        raise ValueError('Unsupported or invalid backup manifest.')
    seen = set()
    for index, record in enumerate(manifest['entries']):
        if not isinstance(record, dict) or not isinstance(record.get('target'), str):
            raise ValueError('Invalid configuration entry in backup manifest.')
        target = Path(record.get('target', ''))
        if target not in allowed or target in seen:
            raise ValueError('Manifest contains an unapproved or duplicate target: ' + str(target))
        seen.add(target)
        source = allowed[target]
        if record.get('backup') != f'{index:03d}-original':
            raise ValueError('Manifest backup entry escapes its backup directory.')
        if record.get('phase') not in ('planned', 'saved', 'installed', 'restored'):
            raise ValueError('Invalid transaction phase.')
        if source is not None:
            if record.get('kind') != 'link' or record.get('expected') != str(source):
                raise ValueError('Manifest link does not match this checkout: ' + str(target))
        elif record.get('kind') != 'file' or not isinstance(record.get('expected'), str) \
                or len(record['expected']) != 64:
            raise ValueError('Invalid personal-settings entry.')
        original = record.get('original')
        if original is not None and (not isinstance(original, list) or len(original) != 3
                                     or any(type(item) is not int for item in original)):
            raise ValueError('Invalid original-file identity.')


def restore(path, allowed):
    """Preflight every target before restoring anything. Retain the manifest."""
    with operation_lock(Path(path).parent):
        return _restore_locked(path, allowed)


def _restore_locked(path, allowed):
    path = Path(path)
    with directory(path) as backup_fd:
        manifest = read(backup_fd)
        validate(manifest, allowed)
        for record in manifest['entries']:
            if record['phase'] == 'restored':
                continue
            target = Path(record['target'])
            with directory(target.parent) as target_fd:
                current = entry_stat(target_fd, target.name)
                saved = entry_stat(backup_fd, record['backup'])
                if saved and identity(saved) != record['original']:
                    raise ValueError('Backup entry was replaced: ' + str(path / record['backup']))
                untouched = (not saved and identity(current) == record['original']
                             and (record['phase'] == 'planned' or manifest['state'] == 'restoring'))
                if untouched:
                    continue
                if record['original'] and not saved:
                    raise ValueError('Original backup is missing: ' + str(path / record['backup']))
                if current and not installed(target_fd, record):
                    raise ValueError('Configuration changed since installation: ' + str(target)
                                     + '. Preserve it elsewhere before restoring ' + str(path))
        manifest['state'] = 'restoring'
        save(backup_fd, manifest)
        for record in reversed(manifest['entries']):
            if record['phase'] == 'restored':
                continue
            target = Path(record['target'])
            with directory(target.parent) as target_fd:
                current = entry_stat(target_fd, target.name)
                saved = entry_stat(backup_fd, record['backup'])
                if saved and identity(saved) != record['original']:
                    raise ValueError('Backup entry changed during restore: ' + str(path / record['backup']))
                if record['original'] and not saved and identity(current) != record['original']:
                    raise ValueError('Original backup disappeared during restore: ' + str(path / record['backup']))
                if saved or not record['original']:
                    if current:
                        if not installed(target_fd, record):
                            raise ValueError('Configuration changed during restore: ' + str(target))
                        os.unlink(target.name, dir_fd=target_fd)
                        os.fsync(target_fd)
                    if saved:
                        move(backup_fd, record['backup'], target_fd, target.name)
                record['phase'] = 'restored'
                save(backup_fd, manifest)
        manifest['state'] = 'restored'
        save(backup_fd, manifest)
    return path


class Transaction:
    def __init__(self, root, changes, allowed):
        self.root, self.changes, self.allowed = Path(root), changes, allowed
        self.path = None

    def apply(self):
        with operation_lock(self.root):
            return self._apply_locked()

    def _apply_locked(self):
        records = []
        for index, change in enumerate(self.changes):
            with directory(change.target.parent, create=True) as descriptor:
                original = identity(entry_stat(descriptor, change.target.name))
            records.append({'target': str(change.target), 'backup': f'{index:03d}-original',
                            'original': original, 'kind': 'link' if change.source else 'file',
                            'expected': str(change.source) if change.source else
                            hashlib.sha256(change.content.encode()).hexdigest(), 'phase': 'planned'})
        manifest = {'version': 1, 'state': 'installing', 'entries': records}
        validate(manifest, self.allowed)
        with directory(self.root, create=True) as root_fd:
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
            os.mkdir(name, mode=0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        self.path = self.root / name
        try:
            with directory(self.path) as backup_fd:
                save(backup_fd, manifest)
                for change, record in zip(self.changes, records):
                    staged = record['backup'] + '-new'
                    if change.source is None:
                        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=backup_fd)
                        with os.fdopen(fd, 'w') as stream:
                            stream.write(change.content)
                            stream.flush()
                            os.fsync(stream.fileno())
                    with directory(change.target.parent) as target_fd:
                        if identity(entry_stat(target_fd, change.target.name)) != record['original']:
                            raise ValueError('Configuration changed during setup: ' + str(change.target))
                        if record['original']:
                            move(target_fd, change.target.name, backup_fd, record['backup'])
                        record['phase'] = 'saved'
                        save(backup_fd, manifest)
                        if change.source:
                            os.symlink(str(change.source), change.target.name, dir_fd=target_fd)
                        else:
                            move(backup_fd, staged, target_fd, change.target.name)
                        os.fsync(target_fd)
                        record['phase'] = 'installed'
                        save(backup_fd, manifest)
                manifest['state'] = 'installed'
                save(backup_fd, manifest)
        except (OSError, ValueError):
            try:
                _restore_locked(self.path, self.allowed)
            except (OSError, ValueError) as error:
                raise ValueError('Setup stopped and rollback needs attention. Backup: '
                                 + str(self.path) + '. ' + str(error)) from error
            raise
        return self.path
