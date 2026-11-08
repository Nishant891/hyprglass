import subprocess
import types
import unittest
from unittest.mock import patch

from hyprglass.install import dependencies


class DependencyTests(unittest.TestCase):
    def inspect(self, hyprland='Hyprland 0.55.1', gtk='[4, 20, 3]', build=False, library='99.0.0'):
        def run(command):
            if command[0] == 'Hyprland':
                return types.SimpleNamespace(returncode=0, stdout=hyprland, stderr='')
            if command[0] == 'pkg-config':
                return types.SimpleNamespace(returncode=0, stdout=library, stderr='')
            return types.SimpleNamespace(returncode=0, stdout=gtk, stderr='')
        with patch.object(dependencies.shutil, 'which', return_value='/usr/bin/tool'), \
                patch.object(dependencies.importlib.util, 'find_spec', return_value=object()), \
                patch.object(dependencies, 'is_arch', return_value=False), \
                patch.object(dependencies, 'run', side_effect=run):
            return dependencies.inspect('kitty', build)

    def test_current_versions_pass_without_arbitrary_upper_bound(self):
        self.assertEqual(self.inspect(hyprland='Hyprland 1.55.0', build=True), [])

    def test_old_hyprland_is_explicit(self):
        issues = self.inspect(hyprland='Hyprland 0.54.3')
        self.assertTrue(any('Hyprland >= 0.55' in issue.message for issue in issues))

    def test_unparseable_hyprland_fails_closed(self):
        issues = self.inspect(hyprland='Hyprland unknown')
        self.assertTrue(any('Could not parse version' in issue.message for issue in issues))

    def test_old_gtk_is_explicit(self):
        issues = self.inspect(gtk='[4, 16, 12]')
        self.assertTrue(any('GTK >= 4.16.13' in issue.message for issue in issues))

    def test_unparseable_gtk_fails_closed(self):
        self.assertTrue(self.inspect(gtk='not a version'))

    def test_unparseable_library_version_fails_closed(self):
        issues = self.inspect(build=True, library='unknown')
        self.assertTrue(any('Could not parse version' in issue.message for issue in issues))

    def test_required_packages_cover_user_facing_features(self):
        required = dependencies.packages('kitty', True)
        for package in ('waybar', 'wofi', 'rofi', 'hyprpaper', 'hyprlock', 'networkmanager',
                        'bluez', 'bluez-utils', 'pipewire', 'pipewire-pulse', 'wireplumber',
                        'hyprshot', 'wf-recorder', 'wl-clipboard', 'playerctl', 'kitty', 'file', 'granite7'):
            self.assertIn(package, required)
        self.assertNotIn('ollama', required)
        self.assertNotIn('python-beautifulsoup4', required)
        self.assertNotIn('ghostty', required)

    def test_pacman_keeps_confirmation_and_uses_full_upgrade(self):
        with patch.object(dependencies, 'is_arch', return_value=True), \
                patch.object(dependencies.shutil, 'which', return_value='/usr/bin/tool'), \
                patch.object(dependencies, 'unsatisfied_packages', return_value=['waybar', 'kitty']), \
                patch.object(dependencies.subprocess, 'run') as run:
            dependencies.install_packages('kitty', False)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ['sudo', 'pacman', '-Syu', '--needed'])
        self.assertNotIn('--noconfirm', command)
        self.assertIn('waybar', command)

    def test_existing_package_providers_are_accepted(self):
        result = types.SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(dependencies, 'run', return_value=result) as run:
            self.assertEqual(dependencies.unsatisfied_packages('kitty', False), [])
        self.assertEqual(run.call_args.args[0][:2], ['pacman', '-T'])

    def test_package_installation_preserves_satisfied_git_providers(self):
        with patch.object(dependencies, 'is_arch', return_value=True), \
                patch.object(dependencies.shutil, 'which', return_value='/usr/bin/tool'), \
                patch.object(dependencies, 'unsatisfied_packages', return_value=['wl-clipboard']), \
                patch.object(dependencies.subprocess, 'run') as run:
            dependencies.install_packages('kitty', False)
        self.assertEqual(run.call_args.args[0], ['sudo', 'pacman', '-Syu', '--needed', 'wl-clipboard'])

    def test_unsupported_distribution_never_runs_package_manager(self):
        with patch.object(dependencies, 'is_arch', return_value=False), \
                patch.object(dependencies.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Arch and ID_LIKE=arch'):
                dependencies.install_packages('kitty', False)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
