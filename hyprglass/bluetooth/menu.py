#!/usr/bin/env python3
"""Rofi Bluetooth picker with a scoped BlueZ pairing agent."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from hyprglass.paths import COMMAND
import time
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from hyprglass.radio.ui import RUNTIME, TOGGLE, choose, notify, read_state, write_state

BLUEZ = 'org.bluez'
CANCEL = RUNTIME / 'hypr-bluetooth-cancel'
AGENT_PATH = '/org/hypr/RadioPairing'

def objects(bus):
    return dbus.Interface(bus.get_object(BLUEZ, '/'), 'org.freedesktop.DBus.ObjectManager').GetManagedObjects()

def props(bus, path):
    return dbus.Interface(bus.get_object(BLUEZ, path), 'org.freedesktop.DBus.Properties')

def discover(bus, adapter, duration=5):
    controller = dbus.Interface(bus.get_object(BLUEZ, adapter), BLUEZ + '.Adapter1')
    controller.StartDiscovery(timeout=3)
    try:
        time.sleep(duration)
    finally:
        controller.StopDiscovery(timeout=3)

class Rejected(dbus.DBusException):
    _dbus_error_name = 'org.bluez.Error.Rejected'

class Agent(dbus.service.Object):
    def __init__(self, bus, name):
        self.name = name
        super().__init__(bus, AGENT_PATH)

    def confirm(self, message):
        if choose('bluetooth-auth', self.name, ['Reject', 'Confirm'], message=message) != 1:
            raise Rejected('Pairing rejected')

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self):
        pass

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        pin = choose('bluetooth-auth', 'Bluetooth PIN', secret=True, message=self.name)
        if not pin:
            raise Rejected('Cancelled')
        return pin

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        pin = self.RequestPinCode(device)
        if not pin.isdigit() or len(pin) > 6:
            raise Rejected('Passkey must contain up to six digits')
        return dbus.UInt32(int(pin))

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pin):
        notify('Bluetooth', f'Enter PIN {pin} on {self.name}')

    @dbus.service.method('org.bluez.Agent1', in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        notify('Bluetooth', f'Enter {int(passkey):06d} on {self.name}')

    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        self.confirm(f'Does {int(passkey):06d} match the code on your device?')

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        self.confirm('Allow this device to pair?')

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        self.confirm('Allow the requested Bluetooth service?')

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        notify('Bluetooth', 'Pairing was cancelled by the device.')

def busy():
    with (RUNTIME / 'hypr-bluetooth-worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True

def worker(job):
    with (RUNTIME / 'hypr-bluetooth-worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        CANCEL.unlink(missing_ok=True)
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        loop = GLib.MainLoop()
        path, name = job['path'], job['name']
        device = dbus.Interface(bus.get_object(BLUEZ, path), BLUEZ+'.Device1')
        agent = Agent(bus, name)
        manager = dbus.Interface(bus.get_object(BLUEZ, '/org/bluez'), BLUEZ+'.AgentManager1')
        manager.RegisterAgent(AGENT_PATH, 'KeyboardDisplay')
        done = False
        started = time.monotonic()

        def finish(error=None):
            nonlocal done
            if done:
                return
            done = True
            text = str(error) if error else f'Connected to {name}'
            write_state('bluetooth', stage='failed' if error else 'connected', name=name, error=str(error or ''))
            notify('Bluetooth', text)
            loop.quit()

        def connect():
            write_state('bluetooth', stage='connecting', name=name)
            device.Connect(reply_handler=lambda: finish(), error_handler=finish, timeout=30)

        def paired():
            props(bus, path).Set(BLUEZ+'.Device1', 'Trusted', dbus.Boolean(True))
            connect()

        def tick():
            if CANCEL.exists() or time.monotonic()-started > 60:
                try:
                    device.CancelPairing(timeout=2)
                except dbus.DBusException:
                    pass
                try:
                    device.Disconnect(timeout=2)
                except dbus.DBusException:
                    pass
                finish('Bluetooth attempt cancelled.' if CANCEL.exists() else 'Bluetooth connection timed out.')
                return False
            return not done

        try:
            if props(bus, path).Get(BLUEZ+'.Device1', 'Paired'):
                connect()
            else:
                write_state('bluetooth', stage='pairing', name=name)
                device.Pair(reply_handler=paired, error_handler=finish, timeout=60)
            GLib.timeout_add(250, tick)
            loop.run()
        finally:
            manager.UnregisterAgent(AGENT_PATH)
            CANCEL.unlink(missing_ok=True)

def main():
    bus = dbus.SystemBus()
    while True:
        if busy():
            state = read_state('bluetooth')
            if choose('bluetooth', 'Bluetooth', ['Close', 'Cancel attempt'],
                      message=f"{state.get('stage','Connecting').title()}: {state.get('name','')}") == 1:
                CANCEL.touch()
            return
        data = objects(bus)
        adapters = [path for path, interfaces in data.items() if BLUEZ+'.Adapter1' in interfaces]
        if not adapters:
            raise RuntimeError('No Bluetooth adapter found.')
        adapter = adapters[0]
        powered = bool(data[adapter][BLUEZ+'.Adapter1']['Powered'])
        devices = [(str(path), values[BLUEZ+'.Device1']) for path, values in data.items()
                   if powered and BLUEZ+'.Device1' in values and str(values[BLUEZ+'.Device1']['Adapter']) == adapter]
        devices.sort(key=lambda item: (not item[1].get('Connected'), not item[1].get('Paired'), str(item[1].get('Alias',''))))
        rows = [f"{'✓' if d.get('Connected') else '○'}  {d.get('Alias',d['Address'])}  ·  {'Connected' if d.get('Connected') else 'Paired' if d.get('Paired') else 'Available'}" for _, d in devices]
        rows += ['↻  Discover Devices', '⏻  Turn Off'] if powered else ['⏻  Turn On']
        index = choose('bluetooth', 'Bluetooth', rows, powered=powered)
        if index is None:
            return
        if index is TOGGLE or index == len(devices) + int(powered):
            try:
                props(bus, adapter).Set(BLUEZ+'.Adapter1', 'Powered', dbus.Boolean(not powered))
            except dbus.DBusException as error:
                notify('Bluetooth', str(error))
            continue
        if index == len(devices):
            try:
                discover(bus, adapter)
            except dbus.DBusException as error:
                notify('Bluetooth', str(error))
            continue
        path, data = devices[index]
        name = str(data.get('Alias',data['Address']))
        if data.get('Connected'):
            action = choose('bluetooth',name,['Close','Disconnect','Forget device…'])
            if action == 1:
                dbus.Interface(bus.get_object(BLUEZ,path),BLUEZ+'.Device1').Disconnect()
            elif action == 2 and choose('bluetooth','Forget '+name+'?', ['Cancel','Forget']) == 1:
                dbus.Interface(bus.get_object(BLUEZ,adapter),BLUEZ+'.Adapter1').RemoveDevice(path)
            return
        job = subprocess.Popen([sys.executable, '-B', str(COMMAND), 'bluetooth', '--worker'],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               text=True,start_new_session=True)
        job.stdin.write(json.dumps(dict(path=path,name=name)))
        job.stdin.close()
        return

if __name__ == '__main__':
    os.umask(0o077)
    try:
        if '--worker' in sys.argv:
            worker(json.load(sys.stdin))
        else:
            with (RUNTIME / 'hypr-bluetooth-menu.lock').open('w') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    sys.exit(0)
                main()
    except (RuntimeError,OSError,dbus.DBusException) as error:
        notify('Bluetooth',str(error))
