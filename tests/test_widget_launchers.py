import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

COMPONENT = Path(__file__).resolve().parents[1] / 'hyprglass/assistant'
spec = importlib.util.spec_from_file_location('desktop_widgets', COMPONENT / 'app.py')
desktop = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, HYPR_WIDGETS_PRELOADED='1'):
    spec.loader.exec_module(desktop)


class LauncherTests(unittest.TestCase):
    def test_missing_sidebar_does_not_block_assistant_or_calendar(self):
        app = SimpleNamespace(cc=Mock())
        app.cc.call_sync.side_effect = desktop.GLib.Error('No owner')
        with patch.object(desktop.subprocess, 'run') as run:
            self.assertIsNone(desktop.Desktop.cc_call(app, 'SetVisibility'))
        run.assert_not_called()

    def test_sidebar_start_retries_against_well_known_name(self):
        app = SimpleNamespace(cc=Mock())
        app.cc.call_sync.side_effect = [desktop.GLib.Error('No owner'), 'opened']
        with patch.object(desktop.subprocess, 'run') as run:
            self.assertEqual(desktop.Desktop.cc_call(app, 'ToggleVisibility', required=True), 'opened')
        self.assertEqual(run.call_args.args[0], ['systemctl', '--user', 'start', 'swaync.service'])
        self.assertEqual(app.cc.call_sync.call_count, 2)
        for call in app.cc.call_sync.call_args_list:
            self.assertEqual(call.args[0], 'org.erikreider.swaync.cc')
            self.assertEqual(call.args[6], desktop.Gio.DBusCallFlags.NO_AUTO_START)

    def test_launch_error_returns_to_caller_instead_of_hanging(self):
        command = Mock(spec=desktop.Gio.ApplicationCommandLine)
        command.get_arguments.return_value = ['desktop-widgets.py', 'panel']
        app = SimpleNamespace(activate_action=Mock(side_effect=desktop.GLib.Error('Failed to start')))
        self.assertEqual(desktop.Desktop.do_command_line(app, command), 1)
        command.printerr_literal.assert_called_once()


if __name__ == '__main__':
    unittest.main()
