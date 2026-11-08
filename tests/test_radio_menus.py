import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import subprocess

from hyprglass.radio import ui as radio_ui
from hyprglass.wifi import menu as wifi
from hyprglass.bluetooth import menu as bt

class RadioTests(unittest.TestCase):
    def test_connection_failure_shows_a_short_message(self):
        detail = 'NetworkManager activation failed: ' + 'technical details ' * 100
        ap = dict(ssid='Phone', security='WPA2')
        with tempfile.TemporaryDirectory() as td, patch.object(wifi, 'RUNTIME', Path(td)), patch.object(wifi, 'CANCEL', Path(td) / 'cancel'):
            with patch.object(wifi, 'current_uuid', return_value='old'), patch.object(wifi, 'access_points', return_value=[ap]), patch.object(wifi, 'run_activation', side_effect=RuntimeError(detail)), patch.object(wifi, 'nm'), patch.object(wifi, 'notify') as notify, patch.object(wifi, 'write_state') as state:
                wifi.worker(dict(device='wlan0', ap=ap, uuid='new', password=None))
        self.assertEqual(state.call_args.kwargs['error'], 'Connection error.')
        self.assertEqual(notify.call_args.args, ('Wi-Fi', 'Connection error.'))

    def test_old_detailed_connection_errors_are_not_shown_in_the_picker(self):
        state = {'stage': 'failed', 'error': 'technical details ' * 100}
        with patch.object(wifi, 'nm', side_effect=['wlan0:wifi', 'enabled']), patch.object(wifi, 'active_job', return_value=False), patch.object(wifi, 'access_points', return_value=[]), patch.object(wifi, 'read_state', return_value=state), patch.object(wifi, 'choose', return_value=None) as choose:
            wifi.main()
        self.assertEqual(choose.call_args.kwargs['message'], 'Connection error.')

    def test_escaped_names_and_active_order(self):
        raw=':90:WPA2:Office\\: west:AA\\:BB\n*:40:WPA2:Office\\: west:CC\\:DD\n:80::Open space:EE\\:FF'
        with patch.object(wifi,'nm',return_value=raw):
            aps=wifi.access_points('wlan0')
        self.assertEqual([a['ssid'] for a in aps],['Office: west','Open space'])
        self.assertTrue(aps[0]['active'])
        self.assertEqual(wifi.fields(r'a\\b:x\:y'),['a\\b','x:y'])

    def test_busy_menu_can_cancel_without_waiting(self):
        with tempfile.TemporaryDirectory() as td, patch.object(wifi,'CANCEL',Path(td)/'cancel'):
            with patch.object(wifi,'nm',return_value='wlan0:wifi'), patch.object(wifi,'active_job',return_value=True), patch.object(wifi,'read_state',return_value={'ssid':'Phone','stage':'connecting'}), patch.object(wifi,'choose',return_value=1), patch.object(wifi,'notify'):
                wifi.main()
            self.assertTrue(wifi.CANCEL.exists())

    def test_password_cancellation_has_no_network_side_effect(self):
        ap=dict(active=False,ssid='Phone',signal=90,security='WPA2',bssid='AA')
        with patch.object(wifi,'nm',side_effect=['wlan0:wifi','enabled']), patch.object(wifi,'active_job',return_value=False), patch.object(wifi,'access_points',return_value=[ap]), patch.object(wifi,'profiles',return_value=[]), patch.object(wifi,'read_state',return_value={}), patch.object(wifi,'choose',side_effect=[0,None]), patch.object(wifi,'start_job') as start:
            wifi.main()
            start.assert_not_called()

    def test_worker_failure_restores_previous_profile(self):
        ap=dict(ssid='Phone',security='WPA2')
        with tempfile.TemporaryDirectory() as td, patch.object(wifi,'RUNTIME',Path(td)), patch.object(wifi,'CANCEL',Path(td)/'cancel'):
            with patch.object(wifi,'current_uuid',side_effect=['old','new']), patch.object(wifi,'access_points',return_value=[ap]), patch.object(wifi,'run_activation',side_effect=RuntimeError('Wrong password')), patch.object(wifi,'nm') as nm, patch.object(wifi,'notify'), patch.object(wifi,'write_state') as state:
                wifi.worker(dict(device='wlan0',ap=ap,uuid='new',password=None))
                self.assertEqual(state.call_args.kwargs['stage'],'failed')
                self.assertEqual(nm.call_args.args,('--wait','20','connection','up','uuid','old','ifname','wlan0'))

    def test_no_fallback_if_hotspot_disappears_before_switch(self):
        with tempfile.TemporaryDirectory() as td, patch.object(wifi,'RUNTIME',Path(td)), patch.object(wifi,'CANCEL',Path(td)/'cancel'):
            with patch.object(wifi,'current_uuid',return_value='old'), patch.object(wifi,'access_points',return_value=[]), patch.object(wifi,'run_activation') as run, patch.object(wifi,'nm') as nm, patch.object(wifi,'notify'), patch.object(wifi,'write_state'):
                wifi.worker(dict(device='wlan0',ap={'ssid':'Gone'},uuid='new',password=None))
                run.assert_not_called(); nm.assert_not_called()

    def test_password_not_in_process_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'nmcli'
            exe.write_text('#!/usr/bin/python3\nimport sys\nassert "test-secret-123" not in " ".join(sys.argv)\np=sys.argv[sys.argv.index("passwd-file")+1]\nassert open(p).read()=="802-11-wireless-security.psk:test-secret-123\\n"\nprint("activated")\n')
            exe.chmod(0o700)
            with patch.object(wifi,'ENV',dict(os.environ,PATH=td+':'+os.environ['PATH'])),patch.object(wifi,'CANCEL',Path(td)/'cancel'):
                wifi.run_activation('wlan0','uuid','test-secret-123')

    def test_bluetooth_confirmation_rejects_by_default(self):
        agent=object.__new__(bt.Agent); agent.name='Phone'
        with patch.object(bt,'choose',return_value=0):
            with self.assertRaises(bt.Rejected): agent.RequestConfirmation('/device',123456)
        with patch.object(bt,'choose',return_value=1) as choose:
            agent.RequestConfirmation('/device',123456)
            self.assertIn('123456',choose.call_args.kwargs['message'])

    def test_toggle_is_independent_of_selection_and_filter(self):
        for stdout in ('', '0\n', '-1\n', 'no devices match\n'):
            for powered in (True, False):
                with self.subTest(stdout=stdout, powered=powered), tempfile.TemporaryDirectory() as td:
                    result = subprocess.CompletedProcess([], 10, stdout, '')
                    with patch.object(radio_ui, 'RUNTIME', Path(td)), patch.object(radio_ui.subprocess, 'run', return_value=result) as run:
                        self.assertIs(radio_ui.choose('wifi', 'Wi-Fi', [], powered=powered), radio_ui.TOGGLE)
                    args = run.call_args.args[0]
                    self.assertEqual(args[args.index('-p') + 1], radio_ui.RADIO_ICONS['wifi'])
                    self.assertEqual(args[args.index('-kb-custom-1') + 1], 'Alt+t')
                    self.assertNotIn('-no-custom', args)
                    self.assertIn('toggle-on.svg' if powered else 'toggle-off.svg', ' '.join(args))

    def test_passwords_and_confirmation_keep_their_context_without_switch(self):
        for rows, secret, stdout in ((None, True, 'secret\n'), (['Reject', 'Confirm'], False, '1\n')):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as td:
                result = subprocess.CompletedProcess([], 0, stdout, '')
                with patch.object(radio_ui, 'RUNTIME', Path(td)), patch.object(radio_ui.subprocess, 'run', return_value=result) as run:
                    value = radio_ui.choose('bluetooth-auth', 'Pair Phone', rows, secret=secret)
                self.assertEqual(value, 'secret' if secret else 1)
                args = run.call_args.args[0]
                self.assertEqual(args[args.index('-p') + 1], 'Pair Phone')
                self.assertNotIn('-kb-custom-1', args)
                self.assertNotIn('button-toggle', ' '.join(args))

    def test_wifi_power_actions_reopen_with_observed_state(self):
        for powered in (True, False):
            for use_toggle in (True, False):
                with self.subTest(powered=powered, use_toggle=use_toggle):
                    radio = ['enabled' if powered else 'disabled', 'disabled' if powered else 'enabled']
                    def nm(*args):
                        if args == ('-t', '-f', 'DEVICE,TYPE', 'device'):
                            return 'wlan0:wifi'
                        if args == ('radio', 'wifi'):
                            return radio.pop(0)
                        return ''
                    selected = radio_ui.TOGGLE if use_toggle else int(powered)
                    with patch.object(wifi, 'nm', side_effect=nm) as command, patch.object(wifi, 'active_job', return_value=False), patch.object(wifi, 'access_points', return_value=[]), patch.object(wifi, 'read_state', return_value={}), patch.object(wifi, 'choose', side_effect=[selected, None]) as choose:
                        wifi.main()
                    self.assertIn(unittest.mock.call('radio', 'wifi', 'off' if powered else 'on'), command.call_args_list)
                    self.assertEqual([call.kwargs['powered'] for call in choose.call_args_list], [powered, not powered])
                    self.assertEqual(choose.call_args_list[0].args[2][-1], '⏻  Turn Off' if powered else '⏻  Turn On')

    def test_wifi_failed_toggle_reopens_with_actual_state(self):
        def nm(*args):
            if args == ('-t', '-f', 'DEVICE,TYPE', 'device'):
                return 'wlan0:wifi'
            if args == ('radio', 'wifi'):
                return 'enabled'
            raise RuntimeError('Radio blocked')
        with patch.object(wifi, 'nm', side_effect=nm), patch.object(wifi, 'active_job', return_value=False), patch.object(wifi, 'access_points', return_value=[]), patch.object(wifi, 'read_state', return_value={}), patch.object(wifi, 'choose', side_effect=[radio_ui.TOGGLE, None]) as choose, patch.object(wifi, 'notify') as notify:
            wifi.main()
        self.assertEqual([call.kwargs['powered'] for call in choose.call_args_list], [True, True])
        notify.assert_called_once_with('Wi-Fi', 'Radio blocked')

    def test_bluetooth_power_actions_reopen_with_observed_state(self):
        adapter = '/org/bluez/hci0'
        for powered in (True, False):
            for use_toggle in (True, False):
                with self.subTest(powered=powered, use_toggle=use_toggle):
                    snapshots = [{adapter: {bt.BLUEZ + '.Adapter1': {'Powered': state}}} for state in (powered, not powered)]
                    selected = radio_ui.TOGGLE if use_toggle else int(powered)
                    with patch.object(bt.dbus, 'SystemBus'), patch.object(bt, 'busy', return_value=False), patch.object(bt, 'objects', side_effect=snapshots), patch.object(bt, 'props') as props, patch.object(bt, 'choose', side_effect=[selected, None]) as choose:
                        bt.main()
                    props.return_value.Set.assert_called_once_with(bt.BLUEZ + '.Adapter1', 'Powered', not powered)
                    self.assertEqual([call.kwargs['powered'] for call in choose.call_args_list], [powered, not powered])
                    self.assertEqual(choose.call_args_list[0].args[2][-1], '⏻  Turn Off' if powered else '⏻  Turn On')

    def test_bluetooth_discovery_waits_then_rebuilds_menu(self):
        adapter = '/org/bluez/hci0'
        before = {adapter: {bt.BLUEZ + '.Adapter1': {'Powered': True}}}
        after = dict(before, **{'/org/bluez/hci0/device': {bt.BLUEZ + '.Device1': {'Adapter': adapter, 'Alias': 'New Headphones', 'Address': 'AA:BB'}}})
        with patch.object(bt.dbus, 'SystemBus') as bus, patch.object(bt, 'busy', return_value=False), patch.object(bt, 'objects', side_effect=[before, after]), patch.object(bt, 'choose', side_effect=[0, None]) as choose, patch.object(bt, 'discover') as scan:
            bt.main()
        self.assertEqual(choose.call_count, 2)
        self.assertIn('New Headphones', choose.call_args.args[2][0])
        scan.assert_called_once_with(bus.return_value, adapter)

    def test_bluetooth_discovery_error_keeps_picker_available(self):
        adapter = '/org/bluez/hci0'
        snapshot = {adapter: {bt.BLUEZ + '.Adapter1': {'Powered': True}}}
        outcomes = [bt.dbus.DBusException('Scan denied'), bt.dbus.DBusException('Adapter unavailable')]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                with patch.object(bt.dbus, 'SystemBus'), patch.object(bt, 'busy', return_value=False), patch.object(bt, 'objects', return_value=snapshot), patch.object(bt, 'choose', side_effect=[0, None]) as choose, patch.object(bt, 'discover', side_effect=outcome), patch.object(bt, 'notify') as notify:
                    bt.main()
                self.assertEqual(choose.call_count, 2)
                notify.assert_called_once_with('Bluetooth', str(outcome))

    def test_bluetooth_discovery_stops_owned_session_after_wait(self):
        controller = Mock()
        with patch.object(bt.dbus, 'Interface', return_value=controller), patch.object(bt.time, 'sleep') as sleep:
            bt.discover(Mock(), '/adapter')
        controller.StartDiscovery.assert_called_once_with(timeout=3)
        sleep.assert_called_once_with(5)
        controller.StopDiscovery.assert_called_once_with(timeout=3)

    def test_bluetooth_discovery_failure_does_not_stop_another_session(self):
        controller = Mock()
        controller.StartDiscovery.side_effect = bt.dbus.DBusException('Blocked')
        with patch.object(bt.dbus, 'Interface', return_value=controller), patch.object(bt.time, 'sleep') as sleep:
            with self.assertRaises(bt.dbus.DBusException):
                bt.discover(Mock(), '/adapter')
        sleep.assert_not_called()
        controller.StopDiscovery.assert_not_called()

    def test_bluetooth_discovery_releases_session_if_wait_interrupted(self):
        controller = Mock()
        with patch.object(bt.dbus, 'Interface', return_value=controller), patch.object(bt.time, 'sleep', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                bt.discover(Mock(), '/adapter')
        controller.StopDiscovery.assert_called_once_with(timeout=3)

if __name__=='__main__': unittest.main()
