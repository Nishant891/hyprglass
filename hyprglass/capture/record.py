#!/usr/bin/env python3
"""Toggle an owned wf-recorder process; SIGINT finalizes its video container."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from hyprglass.paths import COMMAND
from datetime import datetime

RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
LOCK = RUNTIME / 'hypr-screen-record.lock'
STATE = RUNTIME / 'hypr-screen-record.json'

def active():
    with LOCK.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True

def notify(text):
    subprocess.run(['notify-send', '-a', 'Screen recording', 'Screen recording', text], check=False)

def worker():
    with LOCK.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors']))
        monitor = next(m for m in monitors if m['focused'])['name']
        folder = Path.home() / 'Videos' / 'Recordings'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.mp4')
        recorder = subprocess.Popen(['wf-recorder', '-o', monitor, '-f', str(target)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        signal.signal(signal.SIGUSR1, lambda *_: recorder.send_signal(signal.SIGINT) if recorder.poll() is None else None)
        STATE.write_text(json.dumps({'pid': os.getpid(), 'file': str(target)}))
        notify('Recording started. Press Record again to save.')
        _, error = recorder.communicate()
        STATE.unlink(missing_ok=True)
        if recorder.returncode == 0 and target.exists():
            notify('Saved to ' + str(target))
        else:
            notify('Could not record: ' + error.decode(errors='replace')[-240:])

if __name__ == '__main__':
    os.umask(0o077)
    action = sys.argv[1] if len(sys.argv) > 1 else 'toggle'
    if action == '--worker':
        worker()
    elif action == 'status':
        print('true' if active() else 'false')
    elif action in ('toggle', 'start', 'stop'):
        if active():
            if action != 'start':
                try:
                    state = json.loads(STATE.read_text())
                    pid = int(state['pid'])
                    
                    if [str(COMMAND).encode(), b'record', b'--worker'] == Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[2:5]:
                        os.kill(pid, signal.SIGUSR1)
                except (OSError, ValueError, KeyError):
                    pass
        elif action != 'stop':
            subprocess.Popen([sys.executable, '-B', str(COMMAND), 'record', '--worker'],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
