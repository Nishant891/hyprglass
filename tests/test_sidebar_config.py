import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from hyprglass.sidebar import config as sidebar


class SidebarConfigTests(unittest.TestCase):
    def test_backlight_uses_detected_device_and_hides_on_desktops(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'hyprglass/sidebar').mkdir(parents=True)
            source = root / 'hyprglass/sidebar/config.json'
            original = {'widgets': ['volume', 'backlight', 'todo'], 'widget-config': {'backlight': {}}}
            source.write_text(json.dumps(original))
            target = sidebar.create_config(root, root / 'sys')
            self.assertEqual(json.loads(target.read_text())['widgets'], ['volume', 'todo'])
            (root / 'sys/backlight/amdgpu_bl1').mkdir(parents=True)
            target = sidebar.create_config(root, root / 'sys')
            generated = json.loads(target.read_text())
            self.assertIn('backlight', generated['widgets'])
            self.assertEqual(generated['widget-config']['backlight']['device'], 'amdgpu_bl1')
            self.assertEqual(json.loads(source.read_text()), original)

    def test_explicit_device_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'hyprglass/sidebar').mkdir(parents=True)
            source = {'widgets': ['backlight'], 'widget-config': {'backlight': {'device': 'chosen'}}}
            (root / 'hyprglass/sidebar/config.json').write_text(json.dumps(source))
            result = sidebar.create_config(root, root / 'sys')
            self.assertEqual(json.loads(result.read_text()), source)
