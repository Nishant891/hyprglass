from dataclasses import dataclass
import json

from hyprglass.paths import BASE


@dataclass(frozen=True)
class BarGap:
    width: int
    center: float
    bottom: int


def read_bar_gaps():
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi

    Atspi.set_timeout(500, 500)
    config = json.loads((BASE / 'hyprglass/waybar/config').read_text())
    margin_left = config.get('margin-left', 0)
    margin_right = config.get('margin-right', 0)
    margin_top = config.get('margin-top', 0)
    gaps = []
    desktop = Atspi.get_desktop(0)
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        if app.get_name() != 'waybar':
            continue
        for index in range(app.get_child_count()):
            frame = app.get_child_at_index(index)
            layout = frame.get_child_at_index(0)
            if layout is None or layout.get_child_count() != 3:
                continue
            frame_rect = frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            tabs = layout.get_child_at_index(1).get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            resources = layout.get_child_at_index(2).get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            if frame_rect.width > 0 and tabs.width > 0 and resources.x > tabs.x + tabs.width:
                gaps.append(BarGap(
                    frame_rect.width + margin_left + margin_right,
                    margin_left + (tabs.x + tabs.width + resources.x) / 2 - frame_rect.x,
                    margin_top + frame_rect.height,
                ))
    return gaps
