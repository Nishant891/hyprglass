"""Today's Markdown tasks, shared by the widget and the command line helper."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import fcntl
import ctypes
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
import time

CHECKBOX = re.compile(r'^([ \t]*(?:[-+*]|\d+[.)])[ \t]+\[)([ xX])(\](?:[ \t]+|$))(.*?)(\r?\n)?$')
FENCE = re.compile(r'^[ \t]*(`{3,}|~{3,})')

def fence_after(fence, line):
    marker = FENCE.match(line)
    if not marker:
        return fence
    token = marker.group(1)
    remainder = line[marker.end():]
    if fence is not None:
        return None if token[0] == fence[0] and len(token) >= len(fence) and not remainder.strip() else fence
    if token[0] == '`' and '`' in remainder:
        return None
    return token

def exchange_files(first, second):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(first), -100, os.fsencode(second), 2) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))

def retain_history(temporary, path):
    history = path.parent / '.hypr-history'
    history.mkdir(mode=0o700, exist_ok=True)
    saved = history / f'{path.stem}-{time.time_ns()}.md'
    os.rename(temporary, saved)
    copies = sorted((item for item in history.iterdir()
                     if not item.is_symlink() and item.is_file() and
                     re.fullmatch(r'\d{4}-\d{2}-\d{2}-\d+\.md', item.name)),
                    key=lambda item: int(item.stem.rsplit('-', 1)[1]), reverse=True)
    total = 0
    for index, item in enumerate(copies):
        size = item.stat().st_size
        if index and (index >= 10 or total + size > 8 * 1024 * 1024):
            item.unlink()
        else:
            total += size
    return saved

@dataclass(frozen=True)
class Document:
    day: str
    path: Path
    content: bytes

    def checkboxes(self):
        fence = None
        for number, line in enumerate(self.content.decode('utf-8').splitlines(keepends=True), 1):
            next_fence = fence_after(fence, line)
            if fence is not None or next_fence is not None:
                fence = next_fence
                continue
            match = CHECKBOX.match(line)
            if match:
                yield number, line, match

    def has_open_fence(self):
        fence = None
        for line in self.content.decode('utf-8').splitlines():
            fence = fence_after(fence, line)
        return fence is not None

    def tasks(self):
        normalized = self.content.decode('utf-8').splitlines(keepends=True)
        matches = list(self.checkboxes())
        for number, line, match in matches:
            normalized[number - 1] = line[:match.start(2)] + ' ' + line[match.end(2):]
        revision = hashlib.sha256((self.day + '\n' + ''.join(normalized)).encode()).hexdigest()
        return [{'line': number, 'text': match.group(4), 'done': match.group(2).lower() == 'x',
                 'fingerprint': hashlib.sha256(f'{revision}:{number}'.encode()).hexdigest()}
                for number, _, match in matches]

    def snapshot(self):
        return {'date': self.day, 'path': str(self.path), 'tasks': self.tasks()}

    def _task_lines(self, number, fingerprint):
        task = next((task for task in self.tasks() if task['line'] == number), None)
        if task is None or task['fingerprint'] != fingerprint:
            raise ValueError('The note changed. Refresh before changing this task.')
        return self.content.decode('utf-8').splitlines(keepends=True)

    def without_task(self, number, fingerprint):
        lines = self._task_lines(number, fingerprint)
        del lines[number - 1]
        return ''.join(lines).encode('utf-8')

    def with_task_state(self, number, fingerprint, done):
        lines = self._task_lines(number, fingerprint)
        match = CHECKBOX.match(lines[number - 1])
        lines[number - 1] = (lines[number - 1][:match.start(2)] + ('x' if done else ' ')
                             + lines[number - 1][match.end(2):])
        return ''.join(lines).encode('utf-8')

class DailyNotes:
    def __init__(self, root=None, today=None):
        self.root = Path(root or os.environ.get('HYPR_NOTES_DIR', Path.home() / 'notes')).expanduser()
        self.today = today or date.today

    @contextmanager
    def _locked(self):
        directory = self.root / 'daily'
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()))
        identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:20]
        lock_path = runtime / f'hypr-notes-{os.getuid()}-{identity}.lock'
        with lock_path.open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            day = self.today().isoformat()
            path = directory / (day + '.md')
            if path.is_symlink():
                raise ValueError('Daily notes must be regular files, not symbolic links.')
            try:
                content = path.read_bytes()
                mode = stat.S_IMODE(path.stat().st_mode)
            except FileNotFoundError:
                content, mode = None, 0o600
            yield Document(day, path, content or b''), content, mode

    def _write(self, document, before, content, mode):
        document.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.' + document.path.name + '.', dir=document.path.parent)
        recovery = False
        try:
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                current = document.path.read_bytes()
            except FileNotFoundError:
                current = None
            if document.path.is_symlink() or current != before:
                raise ValueError('The note changed in your editor. Refresh and try again.')
            if before is None:
                try:
                    os.link(temporary, document.path)
                except FileExistsError:
                    raise ValueError('The note was created in your editor. Refresh and try again.') from None
            else:
                history = document.path.parent / '.hypr-history'
                history.mkdir(mode=0o700, exist_ok=True)
                exchange_files(temporary, document.path)
                recovery = True
                displaced = Path(temporary).read_bytes()
                if displaced != before:
                    exchange_files(temporary, document.path)
                    saved = retain_history(temporary, document.path)
                    raise ValueError(f'The note changed during save. Both versions were kept; recovery copy: {saved}')
                retain_history(temporary, document.path)
        except (OSError, ValueError) as error:
            if recovery and os.path.lexists(temporary):
                raise ValueError(f'{error}. Recovery copy retained at {temporary}') from error
            raise
        finally:
            if not recovery and os.path.exists(temporary):
                os.unlink(temporary)
        return Document(document.day, document.path, content).snapshot()

    def list(self):
        with self._locked() as (document, _, _):
            return document.snapshot()

    def ensure(self):
        with self._locked() as (document, before, mode):
            if before is not None:
                return document.snapshot()
            return self._write(document, before, b'', mode)

    def add(self, text):
        tasks = [line.strip() for line in text.splitlines() if line.strip()]
        if not tasks:
            raise ValueError('Enter a task first.')
        with self._locked() as (document, before, mode):
            if document.has_open_fence():
                raise ValueError('Close the Markdown code block in your note before adding a task.')
            newline = b'\r\n' if b'\r\n' in document.content else b'\n'
            separator = newline if document.content and not document.content.endswith(b'\n') else b''
            content = document.content + separator + newline.join(('- [ ] ' + task).encode() for task in tasks) + newline
            return self._write(document, before, content, mode)

    def toggle(self, line, fingerprint, done):
        with self._locked() as (document, before, mode):
            content = document.with_task_state(line, fingerprint, done)
            if content == before:
                return document.snapshot()
            return self._write(document, before, content, mode)

    def delete(self, line, fingerprint):
        with self._locked() as (document, before, mode):
            content = document.without_task(line, fingerprint)
            return self._write(document, before, content, mode)
