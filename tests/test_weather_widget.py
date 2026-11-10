from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')

from hyprglass.assistant import weather_widget as widget
from hyprglass.waybar.geometry import BarGap


class WeatherPlacementTests(unittest.TestCase):
    def setUp(self):
        self.rect = SimpleNamespace(x=0, y=0, width=1600, height=900)
        self.monitor = Mock()
        self.monitor.get_geometry.return_value = self.rect
        self.window = SimpleNamespace(monitor=self.monitor, gap=None, geometry=None,
                                      WIDTH=widget.WeatherWindow.WIDTH)
        self.window.position = lambda: widget.WeatherWindow.position(self.window)
        self.controller = SimpleNamespace(closed=False, position_busy=False,
                                          windows={self.monitor: self.window}, run_async=Mock())
        self.controller.positioned = lambda gaps: widget.WeatherWidgets.positioned(self.controller, gaps)
        self.margins = {}
        self.margin_patch = patch.object(widget.Layer, 'set_margin',
                                         side_effect=lambda _window, edge, value: self.margins.update({edge: value}))
        self.margin_patch.start()
        self.addCleanup(self.margin_patch.stop)
        self.window.position()

    def test_label_width_changes_and_missing_bounds_keep_measured_position(self):
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1082.5, 31)])
        measured = dict(self.margins)
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1080, 31)])
        self.assertEqual(self.margins, measured)
        widget.WeatherWidgets.positioned(self.controller, [])
        self.assertEqual(self.margins, measured)
        self.assertIsNotNone(self.window.gap)

    def test_does_not_query_accessibility_after_acquiring_a_position(self):
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1082.5, 31)])
        self.assertTrue(widget.WeatherWidgets.refresh_positions(self.controller))
        self.controller.run_async.assert_not_called()

    def test_resized_monitor_reacquires_placement_below_its_bar(self):
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1082.5, 31)])
        self.rect.width = 1920
        self.window.position()
        self.assertIsNone(self.window.gap)
        self.assertTrue(widget.WeatherWidgets.refresh_positions(self.controller))
        self.controller.run_async.assert_called_once()
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1920, 1290, 35)])
        self.assertEqual(self.margins[widget.Layer.Edge.LEFT], 1290 - self.window.WIDTH // 2)
        self.assertEqual(self.margins[widget.Layer.Edge.TOP], 41)

    def test_moved_monitor_invalidates_same_width_measurement(self):
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1082.5, 31)])
        self.rect.x = 1600
        self.window.position()
        self.assertIsNone(self.window.gap)
        self.assertEqual(self.window.geometry, (1600, 0, 1600, 900))

    def test_shutdown_ignores_pending_layout_result(self):
        self.controller.closed = True
        before = dict(self.margins)
        widget.WeatherWidgets.positioned(self.controller, [BarGap(1600, 1082.5, 31)])
        self.assertEqual(self.margins, before)
        self.assertIsNone(self.window.gap)


if __name__ == '__main__':
    unittest.main()
