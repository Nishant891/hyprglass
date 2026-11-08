import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hyprglass.wallpapers import state as wallpaper


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / 'data'
        self.directory = self.root / 'images'
        self.directory.mkdir()
        for name in ('smile.jpg', 'smiley.jpg', 'Another.PNG'):
            (self.directory / name).write_bytes(b'image')
        self.patch = patch.object(wallpaper, 'DATA', self.data)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_catalog_includes_images_and_ignores_directories_and_notes(self):
        (self.directory / 'notes.md').write_text('notes')
        (self.directory / 'folder.jpg').mkdir()
        self.assertEqual([path.name for path in wallpaper.images(self.directory)],
                         ['Another.PNG', 'smile.jpg', 'smiley.jpg'])

    def test_success_with_empty_ipc_reply_requires_confirmed_active_path(self):
        image = self.directory / 'smile.jpg'
        with patch.object(wallpaper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
                patch.object(wallpaper, 'active_wallpapers', return_value={'eDP-1': image}):
            wallpaper.set_wallpaper('eDP-1', image)
        with patch.object(wallpaper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
                patch.object(wallpaper, 'active_wallpapers', return_value={'eDP-1': self.directory / 'smiley.jpg'}):
            with self.assertRaisesRegex(RuntimeError, 'confirm'):
                wallpaper.set_wallpaper('eDP-1', image)

    def test_apply_persists_selected_monitor_and_syncs_lock_backgrounds(self):
        image = self.directory / 'smile.jpg'
        other = self.directory / 'smiley.jpg'
        with patch.object(wallpaper, 'set_wallpaper'), \
                patch.object(wallpaper, 'active_wallpapers', return_value={'eDP-1': other, 'DP-1': other}):
            wallpaper.apply_wallpaper('eDP-1', image)
        self.assertEqual(json.loads((self.data / 'wallpapers.json').read_text()), {'eDP-1': str(image)})
        lock = (self.data / 'lock-wallpapers.conf').read_text()
        self.assertIn('monitor = eDP-1', lock)
        self.assertIn('monitor = DP-1', lock)
        self.assertEqual(lock.count('blur_passes = 3'), 3)
        paths = [Path(line.split('=', 1)[1].strip()).resolve() for line in lock.splitlines()
                 if line.strip().startswith('path =')]
        self.assertEqual(paths, [image, image, other])

    def test_failed_apply_does_not_overwrite_selection_or_lock(self):
        self.data.mkdir()
        saved = self.data / 'wallpapers.json'
        saved.write_text('{"eDP-1": "original"}')
        lock = self.data / 'lock-wallpapers.conf'
        lock.write_text('original lock')
        with patch.object(wallpaper, 'set_wallpaper', side_effect=RuntimeError('Failed')):
            with self.assertRaises(RuntimeError):
                wallpaper.apply_wallpaper('eDP-1', self.directory / 'smile.jpg')
        self.assertEqual(saved.read_text(), '{"eDP-1": "original"}')
        self.assertEqual(lock.read_text(), 'original lock')

    def test_lock_paths_handle_spaces_commas_and_config_characters(self):
        image = self.directory / 'summer, # {blue}.jpg'
        image.write_bytes(b'image')
        wallpaper.sync_lock_backgrounds({'eDP-1': image})
        lock = (self.data / 'lock-wallpapers.conf').read_text()
        self.assertNotIn('summer', lock)
        links = [path.resolve() for path in (self.data / 'wallpaper-links').iterdir()]
        self.assertIn(image, links)
        self.assertIn(wallpaper.BASE / 'hyprglass/wallpapers/avatar.png', links)

    def test_startup_uses_saved_choice_and_defaults_on_other_output(self):
        image = self.directory / 'Another.PNG'
        monitors = json.dumps([{'name': 'eDP-1'}, {'name': 'DP-1'}])
        with patch.object(wallpaper, 'DIRECTORY', self.directory), \
                patch.object(wallpaper, 'saved_wallpapers', return_value={'eDP-1': image}), \
                patch.object(wallpaper.subprocess, 'check_output', return_value=monitors), \
                patch.object(wallpaper, 'set_wallpaper') as apply, \
                patch.object(wallpaper, 'sync_lock_backgrounds') as sync:
            wallpaper.restore_wallpapers()
        self.assertEqual([call.args for call in apply.call_args_list],
                         [('eDP-1', image), ('DP-1', wallpaper.FALLBACK)])
        sync.assert_called_once()

    def test_empty_wallpaper_folder_is_created_with_default(self):
        directory = self.root / 'Pictures/Wallpaper'
        choices = wallpaper.images(directory)
        self.assertEqual(choices, [directory / 'default.png'])
        self.assertEqual(choices[0].read_bytes(), wallpaper.FALLBACK.read_bytes())

    def test_unused_wallpaper_links_are_removed(self):
        first = self.directory / 'smile.jpg'
        second = self.directory / 'smiley.jpg'
        wallpaper.sync_lock_backgrounds({'eDP-1': first})
        old = wallpaper.image_link(first)
        wallpaper.sync_lock_backgrounds({'eDP-1': second})
        self.assertFalse(old.exists())
        self.assertTrue(wallpaper.image_link(second).exists())

    def test_startup_creates_folder_and_uses_its_single_default(self):
        directory = self.root / 'Pictures/Wallpaper'
        with patch.object(wallpaper, 'DIRECTORY', directory), \
                patch.object(wallpaper, 'saved_wallpapers', return_value={}), \
                patch.object(wallpaper.subprocess, 'check_output', return_value='[{"name":"eDP-1"}]'), \
                patch.object(wallpaper, 'set_wallpaper') as apply, \
                patch.object(wallpaper, 'sync_lock_backgrounds'):
            wallpaper.restore_wallpapers()
        apply.assert_called_once_with('eDP-1', directory / 'default.png')
        self.assertEqual(wallpaper.images(directory), [directory / 'default.png'])

    def test_stale_or_malformed_saved_state_falls_back(self):
        self.data.mkdir()
        path = self.data / 'wallpapers.json'
        for value in ('broken', '[]', '{"eDP-1": 42}', '{"eDP-1": "/does/not/exist"}'):
            path.write_text(value)
            self.assertEqual(wallpaper.saved_wallpapers(), {})


if __name__ == '__main__':
    unittest.main()
