import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from hyprglass.install import backups, dependencies, setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / "home"
        self.source = self.root / "checkout"
        self.source.mkdir()
        self.config = self.home / ".config"
        self.config.mkdir(parents=True)
        (self.source / "local.example.lua").write_text(
            'return {\n    terminal = "ghostty",\n    open_terminal_on_start = false,\n}\n')
        (self.source / "hyprglass/terminal/ghostty").mkdir(parents=True)
        for component, name in (("sidebar", "swaync.service"),
                                ("assistant", "hypr-widgets.service"),
                                ("assistant", "hypr-ollama.service")):
            path = self.source / "hyprglass" / component / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unit")
        self.wallpaper = types.ModuleType("hyprglass.wallpapers.state")
        self.wallpaper.images = lambda: None
        self.wallpaper.sync_lock_backgrounds = lambda _: None
        for item in (patch.object(setup, "BASE", self.source),
                     patch.object(Path, "home", return_value=self.home),
                     patch.dict(os.environ, XDG_CONFIG_HOME=str(self.config)),
                     patch.object(setup.os, "geteuid", return_value=1000),
                     patch.object(setup, "build_is_current", return_value=True),
                     patch.object(setup, "verify_configuration"),
                     patch.object(dependencies, "inspect", return_value=[]),
                     patch.object(dependencies, "unsatisfied_packages", return_value=[]),
                     patch.object(setup.shutil, "which", side_effect=lambda name: "/usr/bin/" + name),
                     patch.object(setup.subprocess, "run"),
                     patch.dict("sys.modules", {"hyprglass.wallpapers.state": self.wallpaper})):
            item.start()
            self.addCleanup(item.stop)

    def run_setup(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = setup.main(list(args))
        return status, output.getvalue() + errors.getvalue()

    def test_full_install_restore_and_repeated_restore(self):
        target = self.config / "hypr"
        target.mkdir()
        (target / "settings").write_text("previous desktop")
        status, output = self.run_setup("--no-packages")
        self.assertEqual(status, 0, output)
        self.assertEqual(target.resolve(), self.source)
        root = self.config / "hypr-backup"
        identifier, state = backups.list_backups(root)[0]
        self.assertEqual(state, "installed")
        manifest = json.loads((root / identifier / "manifest.json").read_text())
        self.assertEqual(manifest["version"], 1)
        self.assertIn("open_terminal_on_start = false", (self.source / "local.lua").read_text())
        self.assertTrue((self.config / "systemd/user/swaync.service").is_symlink())
        for _ in range(2):
            status, output = self.run_setup("--restore", identifier)
            self.assertEqual(status, 0, output)
        self.assertEqual((target / "settings").read_text(), "previous desktop")
        self.assertFalse((self.source / "local.lua").exists())

    def test_plan_and_check_never_write_or_install(self):
        before = list(self.root.rglob("*"))
        missing = [dependencies.Issue("Missing command waybar", ("waybar",))]
        with patch.object(dependencies, "inspect", return_value=missing), \
                patch.object(dependencies, "install_packages") as packages:
            status, output = self.run_setup("--plan")
            self.assertEqual(status, 0, output)
            self.assertIn("waybar", output)
            self.assertEqual(self.run_setup("--check")[0], 1)
            packages.assert_not_called()
        self.assertEqual(list(self.root.rglob("*")), before)

    def test_no_packages_fails_before_files_change(self):
        before = list(self.root.rglob("*"))
        with patch.object(dependencies, "inspect", return_value=[dependencies.Issue("Missing waybar", ("waybar",))]):
            status, output = self.run_setup("--no-packages")
        self.assertEqual(status, 1)
        self.assertIn("sudo pacman -Syu --needed", output)
        self.assertEqual(list(self.root.rglob("*")), before)

    def test_package_installation_rechecks_before_links(self):
        issue = dependencies.Issue("Missing waybar", ("waybar",))
        with patch.object(dependencies, "inspect", side_effect=[[issue], []]) as inspect, \
                patch.object(dependencies, "install_packages") as packages:
            status, output = self.run_setup()
        self.assertEqual(status, 0, output)
        self.assertEqual(inspect.call_count, 2)
        packages.assert_called_once_with("ghostty", True)

    def test_package_upgrade_rechecks_native_library_freshness(self):
        issue = dependencies.Issue('Missing waybar', ('waybar',))
        with patch.object(dependencies, 'inspect', side_effect=[[issue], []]), \
                patch.object(dependencies, 'install_packages'), \
                patch.object(setup, 'build_is_current', side_effect=[True, False, True]) as freshness, \
                patch.object(setup.subprocess, 'run') as run:
            status, output = self.run_setup()
        self.assertEqual(status, 0, output)
        self.assertEqual(freshness.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0],
                         ['bash', str(self.source / 'hyprglass/sidebar/native/build.sh')])

    def test_package_recheck_failure_leaves_config_untouched(self):
        issue = dependencies.Issue("Hyprland is too old", ("hyprland",))
        with patch.object(dependencies, "inspect", return_value=[issue]), \
                patch.object(dependencies, "install_packages"):
            status, output = self.run_setup()
        self.assertEqual(status, 1)
        self.assertIn("No configuration links were changed", output)
        self.assertFalse((self.config / "hypr").exists())

    def test_kitty_choice_preserves_own_config_and_local_settings(self):
        kitty = self.config / "kitty"
        kitty.mkdir()
        (kitty / "kitty.conf").write_text("font_size 14")
        local = self.source / "local.lua"
        original = 'return {\n    terminal = "kitty",\n    internal_scale = 2,\n}\n'
        local.write_text(original)
        status, output = self.run_setup()
        self.assertEqual(status, 0, output)
        self.assertEqual(local.read_text(), original)
        self.assertEqual((kitty / "kitty.conf").read_text(), "font_size 14")
        self.assertFalse((self.config / "ghostty").exists())

    def test_unavailable_terminal_falls_back_and_backs_up_only_assignment_change(self):
        local = self.source / "local.lua"
        original = 'return {\n    terminal = "ghostty",\n    internal_scale = 2,\n}\n'
        local.write_text(original)
        with patch.object(setup.shutil, "which", side_effect=lambda name: "/usr/bin/kitty" if name == "kitty" else None):
            status, output = self.run_setup()
        self.assertEqual(status, 0, output)
        self.assertIn("ghostty is unavailable", output)
        self.assertEqual(local.read_text(), original.replace('"ghostty"', '"kitty"'))
        self.assertFalse((self.config / "ghostty").exists())
        folder = next((self.config / "hypr-backup").iterdir())
        self.assertEqual((folder / "000-original").read_text(), original)

    def test_explicit_terminal_updates_only_terminal_field(self):
        local = self.source / "local.lua"
        original = 'return {\n    terminal = "ghostty", -- chosen terminal\n    internal_scale = 2,\n}\n'
        local.write_text(original)
        status, output = self.run_setup("--terminal", "foot")
        self.assertEqual(status, 0, output)
        self.assertEqual(local.read_text(), original.replace('"ghostty"', '"foot"'))

    def test_inline_terminal_field_is_updated_instead_of_duplicated(self):
        local = self.source / 'local.lua'
        original = 'return { internal_scale = 2, terminal = "kitty" }\n'
        local.write_text(original)
        selected, content, _ = setup.choose_terminal('foot', local)
        self.assertEqual(selected, 'foot')
        self.assertEqual(content, original.replace('"kitty"', '"foot"'))

    def test_commented_terminal_assignment_is_preserved(self):
        local = self.source / 'local.lua'
        original = '--[[\nterminal = "ghostty",\n]]\nreturn { terminal = "kitty" }\n'
        local.write_text(original)
        _, content, _ = setup.choose_terminal('foot', local)
        self.assertEqual(content, original.replace('terminal = "kitty"', 'terminal = "foot"'))

    def test_dynamic_inline_terminal_is_refused_without_editing(self):
        local = self.source / 'local.lua'
        original = 'return { terminal = os.getenv("TERMINAL") }\n'
        local.write_text(original)
        with self.assertRaisesRegex(ValueError, 'literal'):
            setup.choose_terminal('foot', local)
        self.assertEqual(local.read_text(), original)

    def test_terminal_text_inside_another_string_is_ignored(self):
        local = self.source / 'local.lua'
        original = "return { description = 'terminal = \\\"ghostty\\\"', terminal = 'kitty' }\n"
        local.write_text(original)
        _, content, _ = setup.choose_terminal('foot', local)
        self.assertEqual(content, original.replace("terminal = 'kitty'", "terminal = 'foot'"))

    def test_self_install_skips_root_link(self):
        with patch.object(setup, "BASE", self.config / "hypr"):
            source = setup.BASE
            source.mkdir()
            allowed = setup.sources(self.config)
            for target, origin in allowed.items():
                if origin is not None and origin != source:
                    origin.parent.mkdir(parents=True, exist_ok=True)
                    origin.touch()
            self.assertNotIn(self.config / "hypr", [change.target for change in setup.link_changes(self.config, "kitty")])

    def test_daemon_reload_failure_rolls_back_links_and_local_file(self):
        local = self.source / "local.lua"
        original = 'return {\n    terminal = "kitty",\n    internal_scale = 2,\n}\n'
        local.write_text(original)
        target = self.config / "hypr"
        target.mkdir()
        (target / "settings").write_text("previous desktop")
        with patch.object(setup.subprocess, "run", side_effect=[subprocess.CalledProcessError(1, "systemctl"), None]):
            status, output = self.run_setup("--terminal", "foot")
        self.assertEqual(status, 1)
        self.assertIn("Configuration backup", output)
        self.assertEqual(local.read_text(), original)
        self.assertEqual((target / "settings").read_text(), "previous desktop")

    def test_repeat_install_needs_no_additional_backup(self):
        self.assertEqual(self.run_setup()[0], 0)
        root = self.config / "hypr-backup"
        before = backups.list_backups(root)
        status, output = self.run_setup()
        self.assertEqual(status, 0, output)
        self.assertIn("already match", output)
        self.assertEqual(backups.list_backups(root), before)

    def test_custom_xdg_config_home_is_rejected_before_inspection(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.root / "other")), \
                patch.object(dependencies, "inspect") as inspect:
            status, output = self.run_setup("--plan")
        self.assertEqual(status, 1)
        self.assertIn("Custom XDG_CONFIG_HOME is unsupported", output)
        inspect.assert_not_called()

    def test_incompatible_hyprland_configuration_is_rejected_before_links_change(self):
        before = list(self.root.rglob('*'))
        with patch.object(setup, 'verify_configuration', side_effect=ValueError('Hyprland rejected this configuration')):
            status, output = self.run_setup('--no-packages')
        self.assertEqual(status, 1)
        self.assertIn('Hyprland rejected', output)
        self.assertEqual(list(self.root.rglob('*')), before)

    def test_build_freshness_uses_source_digest_and_libraries(self):
        with patch.object(setup, "build_is_current", self.actual_build_is_current):
            destination = self.source / "tools/swaync"
            for name in setup.ARTIFACTS:
                file = destination / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("artifact")
            metadata = {"source": "pinned", "inputs": "digest", "libraries": {"gtk4": "4.20.3"}}
            (destination / "build-metadata.json").write_text(json.dumps(metadata))
            result = types.SimpleNamespace(stdout=json.dumps(metadata))
            with patch.object(setup.subprocess, "run", return_value=result):
                self.assertTrue(setup.build_is_current())
                metadata["inputs"] = "different"
                result.stdout = json.dumps(metadata)
                self.assertFalse(setup.build_is_current())

    actual_build_is_current = staticmethod(setup.build_is_current)


if __name__ == "__main__":
    unittest.main()
