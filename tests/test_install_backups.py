import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprglass.install import backups


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'home/.config'
        self.config.mkdir(parents=True)
        self.backup_root = self.config / 'hypr-backup'
        self.source = self.root / 'checkout'
        self.source.mkdir()
        self.target = self.config / 'hypr'
        self.allowed = {self.target: self.source}

    def install(self, changes=None):
        transaction = backups.Transaction(self.backup_root, changes or [backups.Change(self.target, self.source)],
                                          self.allowed)
        return transaction.apply()

    def test_broken_symlink_round_trip(self):
        self.target.symlink_to(self.root / 'missing')
        path = self.install()
        self.assertEqual((path / '000-original').readlink(), self.root / 'missing')
        backups.restore(path, self.allowed)
        backups.restore(path, self.allowed)
        self.assertEqual(self.target.readlink(), self.root / 'missing')

    def test_overlapping_restore_is_refused_before_original_can_be_deleted(self):
        self.target.write_text('only original copy')
        path = self.install()
        with backups.operation_lock(self.backup_root):
            with self.assertRaisesRegex(ValueError, 'Another installation or restore'):
                backups.restore(path, self.allowed)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual((path / '000-original').read_text(), 'only original copy')
        backups.restore(path, self.allowed)
        self.assertEqual(self.target.read_text(), 'only original copy')

    def test_failed_second_link_rolls_back_first(self):
        self.target.write_text('original')
        other = self.config / 'ghostty'
        self.allowed[other] = self.source
        original = os.symlink
        def create(source, target, **kwargs):
            if target == 'ghostty':
                raise PermissionError('read only')
            return original(source, target, **kwargs)
        with patch.object(backups.os, 'symlink', side_effect=create):
            with self.assertRaises(PermissionError):
                self.install([backups.Change(self.target, self.source), backups.Change(other, self.source)])
        self.assertEqual(self.target.read_text(), 'original')
        self.assertFalse(os.path.lexists(other))

    def test_restore_preflight_preserves_every_target_if_one_was_changed(self):
        other = self.config / 'ghostty'
        self.allowed[other] = self.source
        self.target.write_text('hypr original')
        other.write_text('ghostty original')
        path = self.install([backups.Change(self.target, self.source), backups.Change(other, self.source)])
        other.unlink()
        other.write_text('external edit')
        with self.assertRaisesRegex(ValueError, 'Configuration changed'):
            backups.restore(path, self.allowed)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(other.read_text(), 'external edit')
        self.assertEqual((path / '000-original').read_text(), 'hypr original')

    def test_manifest_cannot_restore_arbitrary_target(self):
        self.target.write_text('original')
        path = self.install()
        manifest_path = path / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        victim = self.root / 'victim'
        victim.write_text('untouched')
        manifest['entries'][0]['target'] = str(victim)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'unapproved'):
            backups.restore(path, self.allowed)
        self.assertEqual(victim.read_text(), 'untouched')

    def test_manifest_cannot_escape_backup_directory(self):
        self.target.write_text('original')
        path = self.install()
        manifest_path = path / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['entries'][0]['backup'] = '../victim'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'escapes'):
            backups.restore(path, self.allowed)
        self.assertTrue(self.target.is_symlink())

    def test_replaced_backup_symlink_is_refused(self):
        self.target.write_text('original')
        path = self.install()
        (path / '000-original').unlink()
        victim = self.root / 'victim'
        victim.write_text('untouched')
        (path / '000-original').symlink_to(victim)
        with self.assertRaisesRegex(ValueError, 'replaced'):
            backups.restore(path, self.allowed)
        self.assertEqual(victim.read_text(), 'untouched')
        self.assertTrue(self.target.is_symlink())

    def test_symlink_parent_is_refused_for_install(self):
        outside = self.root / 'outside'
        outside.mkdir()
        parent = self.config / 'systemd'
        parent.symlink_to(outside, target_is_directory=True)
        target = parent / 'user/test.service'
        self.allowed = {target: self.source}
        with self.assertRaises(OSError):
            self.install([backups.Change(target, self.source)])
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_parent_is_refused_for_restore(self):
        parent = self.config / 'systemd/user'
        parent.mkdir(parents=True)
        target = parent / 'test.service'
        target.write_text('original')
        self.allowed = {target: self.source}
        path = self.install([backups.Change(target, self.source)])
        target.unlink()
        parent.rmdir()
        outside = self.root / 'outside'
        outside.mkdir()
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            backups.restore(path, self.allowed)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((path / '000-original').read_text(), 'original')

    def test_symlink_backup_root_is_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.backup_root.symlink_to(outside, target_is_directory=True)
        self.target.write_text('original')
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(list(outside.iterdir()), [])

    def test_no_clobber_move_preserves_both_entries(self):
        self.target.write_text('original')
        other = self.config / 'occupied'
        other.write_text('existing backup')
        with backups.directory(self.config) as descriptor:
            with self.assertRaises(FileExistsError):
                backups.move(descriptor, self.target.name, descriptor, other.name)
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(other.read_text(), 'existing backup')

    def test_restore_resumes_after_original_move_before_manifest_update(self):
        self.target.write_text('original')
        path = self.install()
        original_save = backups.save
        def save(descriptor, manifest):
            if manifest['entries'][0]['phase'] == 'restored':
                raise OSError('interrupted manifest write')
            return original_save(descriptor, manifest)
        with patch.object(backups, 'save', side_effect=save):
            with self.assertRaises(OSError):
                backups.restore(path, self.allowed)
        self.assertEqual(self.target.read_text(), 'original')
        backups.restore(path, self.allowed)
        self.assertEqual(self.target.read_text(), 'original')

    def test_backup_selection_refuses_parent_and_symlink_escape(self):
        for value in ('..', '../elsewhere', str(self.root / 'other')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                backups.select_backup(self.backup_root, value)


if __name__ == '__main__':
    unittest.main()
