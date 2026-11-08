"""Exercise daily-note behavior without touching the real notebook."""
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
from hyprglass.notes.storage import DailyNotes


class DailyNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.day = date(2026, 10, 29)
        self.notes = DailyNotes(self.root, lambda: self.day)
        self.path = self.root / 'daily' / '2026-10-29.md'

    def tearDown(self):
        self.temp.cleanup()

    def test_create_append_toggle_preserves_markdown_and_mode(self):
        self.assertEqual(self.notes.list()['tasks'], [])
        self.assertFalse(self.path.exists())
        self.notes.ensure()
        original = b'# A day\r\n\r\nArbitrary text \xe2\x98\x83\r\n  * [ ] Keep *format*  \r\n```md\r\n- [ ] sample\r\n```\r\nEnding'
        self.path.write_bytes(original)
        self.path.chmod(0o640)
        self.notes.ensure()
        self.assertEqual(self.path.read_bytes(), original)
        snapshot = self.notes.add('New task\n\nSecond task')
        self.assertEqual([task['text'] for task in snapshot['tasks']], ['Keep *format*  ', 'New task', 'Second task'])
        task = snapshot['tasks'][0]
        self.notes.toggle(task['line'], task['fingerprint'], True)
        expected = original.replace(b'* [ ] Keep', b'* [x] Keep') + b'\r\n- [ ] New task\r\n- [ ] Second task\r\n'
        self.assertEqual(self.path.read_bytes(), expected)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.notes.toggle(task['line'], task['fingerprint'], True)
        self.assertEqual(self.path.read_bytes(), expected)
        self.notes.toggle(task['line'], task['fingerprint'], False)
        self.assertIn(b'* [ ] Keep', self.path.read_bytes())

    def test_delete_selected_task_preserves_markdown_newlines_mode_and_history(self):
        original = (b'# A day\r\n\r\n- [ ] Duplicate\r\n```md\r\n- [ ] Example\r\n```\r\n'
                    b'  2) [X] Duplicate  \r\n  Child paragraph\r\nEnding')
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(original)
        self.path.chmod(0o640)
        task = self.notes.list()['tasks'][1]
        snapshot = self.notes.delete(task['line'], task['fingerprint'])
        self.assertEqual(self.path.read_bytes(), original.replace(b'  2) [X] Duplicate  \r\n', b''))
        self.assertEqual([task['text'] for task in snapshot['tasks']], ['Duplicate'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        history = list((self.path.parent / '.hypr-history').glob('*.md'))
        self.assertEqual([item.read_bytes() for item in history], [original])

    def test_delete_final_task_without_newline_leaves_empty_note(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'- [ ] Last')
        task = self.notes.list()['tasks'][0]
        self.assertEqual(self.notes.delete(task['line'], task['fingerprint'])['tasks'], [])
        self.assertEqual(self.path.read_bytes(), b'')
        with self.assertRaisesRegex(ValueError, 'Refresh'):
            self.notes.delete(task['line'], task['fingerprint'])

    def test_delete_rejects_stale_editor_changes_and_rollover(self):
        task = self.notes.add('Original')['tasks'][0]
        self.path.write_text('- [ ] Original\nEditor paragraph\n')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Refresh'):
            self.notes.delete(task['line'], task['fingerprint'])
        self.assertEqual(self.path.read_bytes(), before)
        self.day = date(2026, 10, 30)
        tomorrow = self.notes.add('Original')
        next_path = Path(tomorrow['path'])
        with self.assertRaisesRegex(ValueError, 'Refresh'):
            self.notes.delete(task['line'], task['fingerprint'])
        self.assertEqual(next_path.read_bytes(), b'- [ ] Original\n')
        self.assertEqual(self.path.read_bytes(), before)

    def test_delete_uses_same_identity_after_completion_toggle(self):
        task = self.notes.add('Original')['tasks'][0]
        self.notes.toggle(task['line'], task['fingerprint'], True)
        self.notes.delete(task['line'], task['fingerprint'])
        self.assertEqual(self.path.read_bytes(), b'')

    def test_delete_preserves_editor_save_at_exchange(self):
        from hyprglass.notes import storage as daily_notes
        task = self.notes.add('Before')['tasks'][0]
        original_exchange = daily_notes.exchange_files
        calls = []
        def editor_save(first, second):
            if not calls:
                self.path.write_text('- [ ] Before\nEditor update\n')
            calls.append(True)
            return original_exchange(first, second)
        with patch('hyprglass.notes.storage.exchange_files', side_effect=editor_save):
            with self.assertRaisesRegex(ValueError, 'Both versions'):
                self.notes.delete(task['line'], task['fingerprint'])
        self.assertEqual(self.path.read_text(), '- [ ] Before\nEditor update\n')
        history = list((self.path.parent / '.hypr-history').glob('*.md'))
        self.assertTrue(any(item.read_bytes() == b'' for item in history))

    def test_cli_delete_returns_snapshot_and_stale_errors_as_json(self):
        env = dict(os.environ, HYPR_NOTES_DIR=str(self.root))
        def command(*arguments):
            return subprocess.run([sys.executable, '-B', str(ROOT / 'bin/hypr-glass'), 'notes', *arguments],
                                  env=env, capture_output=True, text=True, timeout=10)
        added = command('add', 'CLI task')
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        task = json.loads(added.stdout)['tasks'][0]
        deleted = command('delete', str(task['line']), task['fingerprint'])
        self.assertEqual(deleted.returncode, 0, deleted.stdout + deleted.stderr)
        self.assertEqual(json.loads(deleted.stdout)['tasks'], [])
        stale = command('delete', str(task['line']), task['fingerprint'])
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn('Refresh', json.loads(stale.stdout)['error'])

    def test_reading_does_not_create_notebook(self):
        self.notes.list()
        self.assertFalse((self.root / 'daily').exists())

    def test_recovery_history_has_a_fixed_limit(self):
        self.notes.add('First')
        for number in range(15):
            self.notes.add('Task ' + str(number))
        history = list((self.path.parent / '.hypr-history').glob('*.md'))
        self.assertEqual(len(history), 10)
        self.assertEqual(len(self.notes.list()['tasks']), 16)

    def test_stale_task_rejected_after_editor_changes_or_rollover(self):
        task = self.notes.add('Original')['tasks'][0]
        self.path.write_text('# Editor header\n- [ ] Original\n')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Refresh'):
            self.notes.toggle(task['line'], task['fingerprint'], True)
        self.assertEqual(self.path.read_bytes(), before)
        self.day = date(2026, 10, 30)
        tomorrow = self.notes.add('Original')
        self.assertEqual(tomorrow['date'], '2026-10-30')
        with self.assertRaises(ValueError):
            self.notes.toggle(task['line'], task['fingerprint'], True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_editor_edit_during_atomic_write_is_preserved(self):
        self.notes.add('Before')
        original_mkstemp = tempfile.mkstemp
        def editor_change(*args, **kwargs):
            result = original_mkstemp(*args, **kwargs)
            self.path.write_text('# Editor changed it\n- [ ] Before\n')
            return result
        with patch('hyprglass.notes.storage.tempfile.mkstemp', side_effect=editor_change):
            with self.assertRaisesRegex(ValueError, 'editor'):
                self.notes.add('Widget addition')
        self.assertEqual(self.path.read_text(), '# Editor changed it\n- [ ] Before\n')
        self.assertEqual(list(self.path.parent.glob('.*.md.*')), [])

    def test_concurrent_helper_appends_keep_every_task(self):
        env = dict(os.environ, HYPR_NOTES_DIR=str(self.root))
        def add(index):
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'bin/hypr-glass'), 'notes', 'add', f'Task {index}'],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        with ThreadPoolExecutor(max_workers=8) as workers:
            list(workers.map(add, range(16)))
        snapshot = DailyNotes(self.root).list()
        self.assertEqual(len(snapshot['tasks']), 16)
        self.assertEqual({task['text'] for task in snapshot['tasks']}, {f'Task {index}' for index in range(16)})

    def test_unclosed_code_block_refuses_invisible_task(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('# Notes\n```sh\necho hi\n')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'code block'):
            self.notes.add('Buy milk')
        self.assertEqual(self.path.read_bytes(), before)

    def test_editor_save_at_exchange_is_restored_and_both_versions_retained(self):
        from hyprglass.notes import storage as daily_notes
        task = self.notes.add('Before')['tasks'][0]
        original_exchange = daily_notes.exchange_files
        calls = []
        def editor_save(first, second):
            if not calls:
                self.path.write_text('- [ ] Before\nEditor update\n')
            calls.append(True)
            return original_exchange(first, second)
        with patch('hyprglass.notes.storage.exchange_files', side_effect=editor_save):
            with self.assertRaisesRegex(ValueError, 'Both versions'):
                self.notes.toggle(task['line'], task['fingerprint'], True)
        self.assertEqual(self.path.read_text(), '- [ ] Before\nEditor update\n')
        history = list((self.path.parent / '.hypr-history').glob('*.md'))
        self.assertTrue(any('- [x] Before' in p.read_text() for p in history))

    def test_fence_with_trailing_text_stays_open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('```sh\necho hi\n```still code\n- [ ] Not a task\n')
        self.assertEqual(self.notes.list()['tasks'], [])
        with self.assertRaisesRegex(ValueError, 'code block'):
            self.notes.add('Buy milk')

    def test_history_failure_never_deletes_a_displaced_editor_version(self):
        from hyprglass.notes import storage as daily_notes
        self.notes.add('Before')
        original_exchange = daily_notes.exchange_files
        calls = []
        def editor_save(first, second):
            self.path.write_text(f'- [ ] Before\nEditor version {len(calls) + 1}\n')
            calls.append(True)
            original_exchange(first, second)
        with patch('hyprglass.notes.storage.exchange_files', side_effect=editor_save), patch('hyprglass.notes.storage.retain_history', side_effect=OSError('history unavailable')):
            with self.assertRaisesRegex(ValueError, 'Recovery copy retained'):
                self.notes.add('Widget addition')
        files = [self.path] + list(self.path.parent.glob('.*.md.*'))
        contents = [file.read_text() for file in files]
        self.assertTrue(any('Editor version 1' in text for text in contents))
        self.assertTrue(any('Editor version 2' in text for text in contents))

    def test_cli_errors_are_json_and_nonzero(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'bin/hypr-glass'), 'notes', 'toggle', '1', 'old', 'maybe'],
                                env=dict(os.environ, HYPR_NOTES_DIR=str(self.root)), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('error', json.loads(result.stdout))
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
