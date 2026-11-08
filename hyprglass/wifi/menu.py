#!/usr/bin/env python3
"""NetworkManager picker. UI and connection jobs have separate lifetimes."""
import fcntl
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
from hyprglass.paths import COMMAND
import time
import uuid
import dbus
from hyprglass.radio.ui import RUNTIME, TOGGLE, choose, notify, read_state, write_state

ENV = dict(os.environ, LC_ALL='C')
CANCEL = RUNTIME / 'hypr-wifi-cancel'
NM = 'org.freedesktop.NetworkManager'

def nm(*args, timeout=12):
    p = subprocess.run(['nmcli', '--colors', 'no', *args], capture_output=True,
                       text=True, env=ENV, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return p.stdout.rstrip('\n')

def fields(line):
    result, value, escaped = [], '', False
    for char in line:
        if escaped:
            value += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            result.append(value)
            value = ''
        else:
            value += char
    return result + [value]

def access_points(device, rescan='no'):
    raw = nm('-t', '-f', 'IN-USE,SIGNAL,SECURITY,SSID,BSSID', 'device', 'wifi', 'list',
             'ifname', device, '--rescan', rescan)
    best = {}
    for line in raw.splitlines():
        row = fields(line)
        if len(row) != 5 or not row[3]:
            continue
        active, strength, security, ssid, bssid = row
        ap = dict(active=active == '*', signal=int(strength), security=security,
                  ssid=ssid, bssid=bssid)
        key = (ssid, security)
        if key not in best or (ap['active'], ap['signal']) > (best[key]['active'], best[key]['signal']):
            best[key] = ap
    return sorted(best.values(), key=lambda a: (not a['active'], -a['signal'], a['ssid']))

def profiles(ssid):
    bus = dbus.SystemBus()
    settings = dbus.Interface(bus.get_object(NM, '/org/freedesktop/NetworkManager/Settings'), NM+'.Settings')
    matches = []
    for path in settings.ListConnections():
        obj = dbus.Interface(bus.get_object(NM, path), NM+'.Settings.Connection')
        try:
            values = obj.GetSettings()
        except dbus.DBusException:
            continue
        wifi = values.get('802-11-wireless', {})
        if bytes(wifi.get('ssid', [])).decode('utf-8', errors='replace') == ssid:
            c = values['connection']
            matches.append((int(c.get('timestamp', 0)), str(c['uuid'])))
    return [item[1] for item in sorted(matches, reverse=True)]

def new_profile(ap, password):
    security = ap['security']
    if '802.1X' in security or 'EAP' in security or 'WEP' in security:
        raise RuntimeError('This network needs a configured enterprise/WEP profile before it can be used here.')
    ident = str(uuid.uuid4())
    values = {
        'connection': {'id': ap['ssid'], 'uuid': ident, 'type': '802-11-wireless',
                       'permissions': dbus.Array([f'user:{getpass.getuser()}:'], signature='s'),
                       'autoconnect': dbus.Boolean(False)},
        '802-11-wireless': {'ssid': dbus.ByteArray(ap['ssid'].encode()), 'mode': 'infrastructure'},
        'ipv4': {'method': 'auto'}, 'ipv6': {'method': 'auto'},
    }
    if security and security != '--':
        key = 'owe' if 'OWE' in security else ('sae' if 'WPA3' in security and 'WPA2' not in security else 'wpa-psk')
        values['802-11-wireless-security'] = {'key-mgmt': key}
        if key != 'owe':
            if not password:
                raise RuntimeError('A Wi-Fi password is required.')
            values['802-11-wireless-security']['psk'] = password
    bus = dbus.SystemBus()
    settings = dbus.Interface(bus.get_object(NM, '/org/freedesktop/NetworkManager/Settings'), NM+'.Settings')
    settings.AddConnection(dbus.Dictionary({key: dbus.Dictionary(val, signature='sv')
                                          for key, val in values.items()}, signature='sa{sv}'))
    return ident

def current_uuid(device):
    value = nm('-g', 'GENERAL.CON-UUID', 'device', 'show', device)
    return '' if value == '--' else value

def active_job():
    
    with (RUNTIME / 'hypr-wifi-worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True

def run_activation(device, ident, password):
    args = ['nmcli', '--colors', 'no', '--wait', '30', 'connection', 'up', 'uuid', ident, 'ifname', device]
    read_fd = write_fd = None
    if password:
        read_fd, write_fd = os.pipe()
        os.write(write_fd, ('802-11-wireless-security.psk:' + password + '\n').encode())
        os.close(write_fd)
        args += ['passwd-file', f'/proc/self/fd/{read_fd}']
    try:
        proc = subprocess.Popen(args, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, pass_fds=(() if read_fd is None else (read_fd,)))
    finally:
        if read_fd is not None:
            os.close(read_fd)
    deadline = time.monotonic() + 35
    try:
        while proc.poll() is None:
            if CANCEL.exists():
                raise RuntimeError('Connection cancelled.')
            if time.monotonic() > deadline:
                raise RuntimeError('Connection timed out. The hotspot may be unavailable or authentication failed.')
            time.sleep(.2)
        output = proc.stdout.read()
        if password:
            output = output.replace(password, '[hidden]')
        if proc.returncode:
            raise RuntimeError(output.strip() or 'Connection failed.')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        proc.stdout.close()

def worker(job):
    with (RUNTIME / 'hypr-wifi-worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            notify('Wi-Fi', 'An attempt is already running. Open Wi-Fi to cancel it.')
            return
        CANCEL.unlink(missing_ok=True)
        device, ap = job['device'], job['ap']
        previous, ident = '', job.get('uuid')
        write_state('wifi', stage='connecting', ssid=ap['ssid'])
        try:
            previous = current_uuid(device)
            
            available = access_points(device)
            if not any(a['ssid'] == ap['ssid'] for a in available):
                raise RuntimeError('The hotspot is no longer visible. Turn it on and choose Refresh networks.')
            ident = ident or new_profile(ap, job.get('password'))
            notify('Wi-Fi', f"Connecting to {ap['ssid']}… Open Wi-Fi to view or cancel.")
            run_activation(device, ident, job.get('password'))
            if current_uuid(device) != ident:
                raise RuntimeError('NetworkManager did not activate the selected connection.')
            if not job.get('uuid'):
                nm('connection', 'modify', 'uuid', ident, 'connection.autoconnect', 'yes')
            write_state('wifi', stage='connected', ssid=ap['ssid'])
            notify('Wi-Fi', f"Connected to {ap['ssid']}")
        except (RuntimeError, OSError, subprocess.SubprocessError, dbus.DBusException) as error:
            text = 'Connection error.'
            write_state('wifi', stage='restoring', ssid=ap['ssid'], error=text)
            
            
            try:
                current = current_uuid(device)
                if ident and current == ident and ident != previous:
                    nm('--wait', '5', 'connection', 'down', 'uuid', ident)
                    current = ''
                if previous and current in ('', ident) and current != previous:
                    nm('--wait', '20', 'connection', 'up', 'uuid', previous, 'ifname', device, timeout=25)
            except (RuntimeError, OSError, subprocess.SubprocessError):
                pass
            write_state('wifi', stage='failed', ssid=ap['ssid'], error=text)
            notify('Wi-Fi', text)
        finally:
            CANCEL.unlink(missing_ok=True)

def start_job(device, ap, ident, password):
    proc = subprocess.Popen([sys.executable, '-B', str(COMMAND), 'wifi', '--worker'],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            text=True, start_new_session=True)
    
    proc.stdin.write(json.dumps(dict(device=device, ap=ap, uuid=ident, password=password)))
    proc.stdin.close()

def main():
    devices = [fields(row)[0] for row in nm('-t', '-f', 'DEVICE,TYPE', 'device').splitlines()
               if fields(row)[-1] == 'wifi']
    if not devices:
        raise RuntimeError('No Wi-Fi interface is present. Network services have not been changed.')
    device = devices[0]
    while True:
        if active_job():
            state = read_state('wifi')
            action = choose('wifi', 'Wi-Fi connection', ['Close', 'Cancel connection attempt'],
                            message=f"{state.get('stage', 'Connecting').title()}: {state.get('ssid', '')}")
            if action == 1:
                CANCEL.touch()
                notify('Wi-Fi', 'Cancelling this attempt and restoring the previous connection…')
            return
        powered = nm('radio', 'wifi') == 'enabled'
        aps = access_points(device) if powered else []
        rows = [f"{'✓' if a['active'] else '○'}  {a['ssid']}  ·  {a['signal']}%  ·  {a['security'] or 'Open'}" for a in aps]
        rows += ['↻  Refresh Network', '⏻  Turn Off'] if powered else ['⏻  Turn On']
        state = read_state('wifi')
        message = ''
        if state.get('stage') == 'failed':
            message = 'Connection error.'
        choice = choose('wifi', 'Wi-Fi', rows, message=message, powered=powered)
        if choice is None:
            return
        if choice is TOGGLE or choice == len(aps) + int(powered):
            try:
                nm('radio', 'wifi', 'off' if powered else 'on')
            except (RuntimeError, subprocess.SubprocessError) as error:
                notify('Wi-Fi', str(error))
            continue
        if choice == len(aps):
            try:
                nm('--wait', '8', 'device', 'wifi', 'rescan', 'ifname', device)
                time.sleep(1)
            except RuntimeError as error:
                notify('Wi-Fi', str(error))
            continue
        ap = aps[choice]
        if ap['active']:
            notify('Wi-Fi', f"Already connected to {ap['ssid']}")
            return
        saved = profiles(ap['ssid'])
        ident = saved[0] if saved else None
        password = None
        secure = bool(ap['security'] and ap['security'] != '--' and 'OWE' not in ap['security'])
        if saved and secure:
            action = choose('wifi', ap['ssid'], ['Connect with saved password', 'Enter a different password', 'Cancel'])
            if action is None or action == 2:
                return
            ask = action == 1
        else:
            ask = secure
        if ask:
            password = choose('wifi', 'Password · '+ap['ssid'], secret=True,
                              message='Enter the hotspot password. Esc cancels before changing connections.')
            if not password:
                return
        start_job(device, ap, ident, password)
        return

if __name__ == '__main__':
    os.umask(0o077)
    try:
        if '--worker' in sys.argv:
            worker(json.load(sys.stdin))
        else:
            main()
    except (RuntimeError, OSError, subprocess.SubprocessError, dbus.DBusException) as error:
        notify('Wi-Fi', str(error))
